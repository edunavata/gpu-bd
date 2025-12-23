from __future__ import annotations

import argparse
import json
import logging
import os
import random
import re
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import urljoin
from uuid import uuid4

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://geizhals.de/"
CATEGORY = "gra16_512"
LISTING_URL_TEMPLATE = "https://geizhals.de/?cat=gra16_512&pg={page}"
OUTPUT_ROOT = Path("data/bronze/gpu/marketplace/geizhals/runs")


def _get_env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _get_env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


MIN_DELAY_S = _get_env_float("GEIZHALS_MIN_DELAY_S", 5.0)
MAX_DELAY_S = _get_env_float("GEIZHALS_MAX_DELAY_S", 15.0)
MAX_RETRIES = _get_env_int("GEIZHALS_MAX_RETRIES", 5)
BACKOFF_BASE_S = _get_env_float("GEIZHALS_BACKOFF_BASE_S", 10.0)
BACKOFF_MAX_S = _get_env_float("GEIZHALS_BACKOFF_MAX_S", 120.0)
BACKOFF_JITTER_S = _get_env_float("GEIZHALS_BACKOFF_JITTER_S", 5.0)
CONNECT_TIMEOUT_S = _get_env_float("GEIZHALS_CONNECT_TIMEOUT_S", 10.0)
READ_TIMEOUT_S = _get_env_float("GEIZHALS_READ_TIMEOUT_S", 30.0)
SESSION_ROTATE_EVERY = _get_env_int("GEIZHALS_SESSION_ROTATE_EVERY", 5)
UA_ROTATE_EVERY = max(_get_env_int("GEIZHALS_UA_ROTATE_EVERY", 1), 1)
MIN_HTML_LENGTH = _get_env_int("GEIZHALS_MIN_HTML_LENGTH", 5000)
MAX_PRICE_EUR = _get_env_float("GEIZHALS_MAX_PRICE_EUR", 20000.0)
LOG_LEVEL = os.getenv("GEIZHALS_LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("geizhals.listing")

BASE_HEADERS = {
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
}

USER_AGENT_POOL = [
    {
        "ua": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/121.0.0.0 Safari/537.36"
        ),
        "sec_ch_ua": (
            '"Not.A/Brand";v="8", "Chromium";v="121", ' '"Google Chrome";v="121"'
        ),
        "sec_ch_platform": '"Windows"',
        "sec_ch_mobile": "?0",
    },
    {
        "ua": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6_4) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) "
            "Version/17.2 Safari/605.1.15"
        ),
        "sec_ch_ua": None,
        "sec_ch_platform": '"macOS"',
        "sec_ch_mobile": "?0",
    },
    {
        "ua": (
            "Mozilla/5.0 (X11; Linux x86_64; rv:121.0) " "Gecko/20100101 Firefox/121.0"
        ),
        "sec_ch_ua": None,
        "sec_ch_platform": '"Linux"',
        "sec_ch_mobile": "?0",
    },
    {
        "ua": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Edg/121.0.0.0 Safari/537.36"
        ),
        "sec_ch_ua": (
            '"Not.A/Brand";v="8", "Chromium";v="121", ' '"Microsoft Edge";v="121"'
        ),
        "sec_ch_platform": '"Windows"',
        "sec_ch_mobile": "?0",
    },
]

RETRY_STATUS_CODES = {429, 500, 502, 503, 504}
BOT_KEYWORDS = (
    "captcha",
    "access denied",
    "unusual traffic",
    "verify you are human",
    "robot",
    "bot protection",
    "cloudflare",
    "akamai",
    "attention required",
    "just a moment",
)


PRICE_CLEAN_RE = re.compile(r"[^\d,\.]")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run_timestamp_iso(ts: datetime) -> str:
    return ts.strftime("%Y-%m-%dT%H-%M-%SZ")


def _sleep_with_jitter(min_s: float, max_s: float) -> float:
    if max_s <= 0:
        return 0.0
    low = max(0.0, min_s)
    high = max(low, max_s)
    delay = random.uniform(low, high)
    time.sleep(delay)
    return delay


def _parse_retry_after(header_value: Optional[str]) -> Optional[float]:
    if not header_value:
        return None
    try:
        seconds = int(header_value)
        return max(0.0, float(seconds))
    except ValueError:
        pass
    try:
        parsed = parsedate_to_datetime(header_value)
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    delta = (parsed - datetime.now(timezone.utc)).total_seconds()
    return max(0.0, delta)


def _compute_backoff(attempt: int, retry_after: Optional[float]) -> float:
    exponential = BACKOFF_BASE_S * (2 ** max(attempt - 1, 0))
    capped = min(exponential, BACKOFF_MAX_S)
    jitter = random.uniform(0.0, BACKOFF_JITTER_S)
    wait_s = capped + jitter
    if retry_after is not None:
        wait_s = max(wait_s, retry_after)
    return wait_s


def _choose_user_agent(state: dict[str, object]) -> dict[str, Optional[str]]:
    remaining = state.get("remaining", 0)
    current = state.get("current")
    if not isinstance(remaining, int) or remaining <= 0 or current is None:
        current = random.choice(USER_AGENT_POOL)
        remaining = UA_ROTATE_EVERY
    state["current"] = current
    state["remaining"] = max(remaining - 1, 0)
    return current


def _choose_referer(page_number: int) -> str:
    candidates = [
        BASE_URL,
        LISTING_URL_TEMPLATE.format(page=max(1, page_number - 1)),
    ]
    return random.choice(candidates)


def _build_headers(ua_entry: dict[str, Optional[str]], referer: str) -> dict[str, str]:
    headers = dict(BASE_HEADERS)
    headers["User-Agent"] = ua_entry["ua"] or ""
    headers["Referer"] = referer
    if ua_entry.get("sec_ch_ua"):
        headers["Sec-CH-UA"] = ua_entry["sec_ch_ua"] or ""
        headers["Sec-CH-UA-Platform"] = ua_entry["sec_ch_platform"] or ""
        headers["Sec-CH-UA-Mobile"] = ua_entry["sec_ch_mobile"] or ""
    return headers


def _is_html_sane(html: Optional[str]) -> bool:
    if not html:
        return False
    if len(html) < MIN_HTML_LENGTH:
        return False
    return True


def _looks_like_block_page(html: str) -> bool:
    lowered = html.lower()

    # 1. Verificar Título explícito (Señal fuerte de bloqueo)
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    if title_match:
        title_text = title_match.group(1).strip().lower()
        # Solo palabras muy obvias en el título
        if any(k in title_text for k in ["access denied", "robot", "human", "captcha"]):
            return True

    # 2. Verificar contenido esperado (Si están los productos, NO estamos bloqueados)
    has_products = ("galleryview__item" in html) or ("productlist__product" in html)
    if has_products:
        return False  # <--- Si vemos productos, ignoramos cualquier mención a "captcha" en el footer

    # 3. Solo buscar palabras clave en el cuerpo si NO hay productos y el HTML es sospechoso
    if len(html) < (MIN_HTML_LENGTH * 3):  # Aumentar un poco el margen
        if any(keyword in lowered for keyword in BOT_KEYWORDS):
            return True

    return False


def _is_valid_price(price: Optional[float]) -> bool:
    if price is None:
        return False
    return 0 < price <= MAX_PRICE_EUR


def _atomic_write_text(path: Path, text: str, encoding: str = "utf-8") -> None:
    tmp_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    tmp_path.write_text(text, encoding=encoding)
    tmp_path.replace(path)


def _atomic_write_json(path: Path, payload: object) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    _atomic_write_text(path, text, encoding="utf-8")


def _warmup_session(session: requests.Session, ua_state: dict[str, object]) -> int:
    ua_entry = _choose_user_agent(ua_state)
    headers = _build_headers(ua_entry, BASE_URL)
    try:
        session.get(
            BASE_URL, headers=headers, timeout=(CONNECT_TIMEOUT_S, READ_TIMEOUT_S)
        )
        return 1
    except requests.RequestException:
        logger.info("warmup_failed base_url=%s", BASE_URL)
        return 1


def _prepare_run_dir() -> tuple[Path, datetime]:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    run_dt = datetime.now(timezone.utc).replace(microsecond=0)
    run_dir = OUTPUT_ROOT / _run_timestamp_iso(run_dt)
    while run_dir.exists():
        run_dt += timedelta(seconds=1)
        run_dir = OUTPUT_ROOT / _run_timestamp_iso(run_dt)
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir, run_dt


def _normalize_text(text: str) -> str:
    return " ".join(text.split())


def _parse_price_eur(text: str) -> Optional[float]:
    cleaned = PRICE_CLEAN_RE.sub("", text)
    if not cleaned:
        return None
    if "," in cleaned:
        number = cleaned.replace(".", "").replace(",", ".")
    else:
        number = cleaned.replace(".", "")
    try:
        return float(number)
    except ValueError:
        return None


def _extract_name_and_url(item) -> tuple[Optional[str], Optional[str]]:
    selectors = [
        "a.galleryview__name-link",
        ".productlist__name a",
        "a.productlist__link",
        "h3 a",
    ]
    for selector in selectors:
        link = item.select_one(selector)
        if not link:
            continue
        href = link.get("href")
        name_text = _normalize_text(link.get_text(" ", strip=True))
        if href and name_text:
            return name_text, urljoin(BASE_URL, href)
    return None, None


def _extract_price(item) -> Optional[float]:
    selectors = [
        ".galleryview__price .price",
        ".productlist__price .price",
        ".productlist__price .gh_price",
        ".gh_price",
        ".price",
    ]
    for selector in selectors:
        el = item.select_one(selector)
        if not el:
            continue
        text = el.get_text(" ", strip=True)
        price = _parse_price_eur(text)
        if price is not None:
            return price
    return None


def _parse_items(items: Iterable, page_number: int, scrape_run_id: str) -> list[dict]:
    products: list[dict] = []
    for position, item in enumerate(items, start=1):
        try:
            name, url = _extract_name_and_url(item)
            if not name or not url:
                continue
            price = _extract_price(item)
            if not _is_valid_price(price):
                continue
            products.append(
                {
                    "retailer": "geizhals",
                    "product_name_raw": name,
                    "product_url": url,
                    "price_eur": price,
                    "currency": "EUR",
                    "page_number": page_number,
                    "position_in_page": position,
                    "observed_at_utc": _utc_now_iso(),
                    "scrape_run_id": scrape_run_id,
                }
            )
        except Exception:
            continue
    return products


def parse_products(html: str, page_number: int, scrape_run_id: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    gallery_items = soup.select("article.galleryview__item")
    if gallery_items:
        return _parse_items(gallery_items, page_number, scrape_run_id)
    list_items = soup.select(".productlist__product")
    if list_items:
        return _parse_items(list_items, page_number, scrape_run_id)
    return []


def fetch_listing_page(
    session: requests.Session,
    page_number: int,
    headers: dict[str, str],
    timeout: tuple[float, float] = (CONNECT_TIMEOUT_S, READ_TIMEOUT_S),
) -> tuple[str, int, Optional[str], str, int, bool]:
    url = LISTING_URL_TEMPLATE.format(page=page_number)
    attempts = 0
    last_status = 0
    last_html: Optional[str] = None
    last_fetched_at = _utc_now_iso()
    is_ok = False

    for attempt in range(1, MAX_RETRIES + 2):
        attempts += 1
        try:
            resp = session.get(url, headers=headers, timeout=timeout)
            resp.encoding = "utf-8"
            last_html = resp.text
            last_status = resp.status_code
            last_fetched_at = _utc_now_iso()
        except requests.RequestException:
            last_status = 0
            last_html = None
            last_fetched_at = _utc_now_iso()
            if attempt <= MAX_RETRIES:
                wait_s = _compute_backoff(attempt, None)
                logger.info(
                    "retrying request reason=exception attempt=%s wait_s=%.2f url=%s",
                    attempt,
                    wait_s,
                    url,
                )
                time.sleep(wait_s)
                continue
            break

        retry_after = _parse_retry_after(resp.headers.get("Retry-After"))
        if last_status in RETRY_STATUS_CODES:
            if attempt <= MAX_RETRIES:
                wait_s = _compute_backoff(attempt, retry_after)
                logger.info(
                    "retrying request reason=status status=%s attempt=%s wait_s=%.2f url=%s",
                    last_status,
                    attempt,
                    wait_s,
                    url,
                )
                time.sleep(wait_s)
                continue
            break

        if not _is_html_sane(last_html):
            if attempt <= MAX_RETRIES:
                wait_s = _compute_backoff(attempt, retry_after)
                logger.info(
                    "retrying request reason=short_html status=%s attempt=%s wait_s=%.2f url=%s",
                    last_status,
                    attempt,
                    wait_s,
                    url,
                )
                time.sleep(wait_s)
                continue
            break

        if last_html and _looks_like_block_page(last_html):
            if attempt <= MAX_RETRIES:
                # --- NUEVO: Guardar evidencia para depuración ---
                debug_path = Path(f"debug_block_attempt_{attempt}.html")
                debug_path.write_text(last_html, encoding="utf-8")
                # -----------------------------------------------
                wait_s = _compute_backoff(attempt, retry_after)
                logger.info(...)
                time.sleep(wait_s)
                continue
            break

        is_ok = True
        break

    return url, last_status, last_html, last_fetched_at, attempts, is_ok


def write_json(path: Path, payload: object) -> None:
    _atomic_write_json(path, payload)


def process_pages(pages: Iterable[int]) -> None:
    run_dir, run_started_dt = _prepare_run_dir()
    scrape_run_id = str(uuid4())
    run_started_at = run_started_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    session = requests.Session()
    ua_state: dict[str, object] = {"current": None, "remaining": 0}
    request_tally = 0
    request_tally += _warmup_session(session, ua_state)

    for index, page_number in enumerate(pages):
        if request_tally >= SESSION_ROTATE_EVERY:
            logger.info("session_reset requests=%s", request_tally)
            session.close()
            session = requests.Session()
            request_tally = 0
            request_tally += _warmup_session(session, ua_state)

        if index > 0:
            _sleep_with_jitter(MIN_DELAY_S, MAX_DELAY_S)

        ua_entry = _choose_user_agent(ua_state)
        referer = _choose_referer(page_number)
        headers = _build_headers(ua_entry, referer)

        url, status, html, fetched_at, attempts, ok = fetch_listing_page(
            session,
            page_number,
            headers,
        )
        request_tally += attempts
        html_path = run_dir / f"page_pg={page_number}.html"
        if html is not None:
            _atomic_write_text(html_path, html, encoding="utf-8")

        products: list[dict] = []
        if html and ok:
            try:
                products = parse_products(html, page_number, scrape_run_id)
            except Exception:
                products = []

        status_meta = status
        if not ok and status_meta == 200:
            status_meta = 0

        meta = {
            "page_number": page_number,
            "url": url,
            "fetched_at_utc": fetched_at,
            "http_status": status_meta,
            "product_count": len(products),
        }
        write_json(run_dir / f"page_pg={page_number}.meta.json", meta)
        write_json(run_dir / f"page_pg={page_number}.products.json", products)

    run_meta = {
        "source": "geizhals",
        "entity": "gpu",
        "category": CATEGORY,
        "scrape_run_id": scrape_run_id,
        "started_at_utc": run_started_at,
        "finished_at_utc": _utc_now_iso(),
    }
    write_json(run_dir / "run.meta.json", run_meta)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch Geizhals GPU listing pages into bronze evidence."
    )
    parser.add_argument(
        "pages",
        nargs="+",
        type=int,
        help="Page numbers to fetch (e.g. 1 2 3).",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    pages = args.pages
    for page_number in pages:
        if page_number < 1:
            raise ValueError("Page numbers must be >= 1.")
    process_pages(pages)


if __name__ == "__main__":
    main()
