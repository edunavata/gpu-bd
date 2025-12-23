from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import urljoin
from uuid import uuid4

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://geizhals.de/"
CATEGORY = "gra16_512"
LISTING_URL_TEMPLATE = "https://geizhals.de/?cat=gra16_512&pg={page}"
OUTPUT_ROOT = Path("data/bronze/geizhals/gpu/runs")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
}


PRICE_CLEAN_RE = re.compile(r"[^\d,\.]")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run_timestamp_iso(ts: datetime) -> str:
    return ts.strftime("%Y-%m-%dT%H-%M-%SZ")


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
            if price is None:
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
    timeout_s: float = 25.0,
) -> tuple[str, int, Optional[str], str]:
    url = LISTING_URL_TEMPLATE.format(page=page_number)
    try:
        resp = session.get(url, headers=HEADERS, timeout=timeout_s)
        resp.encoding = "utf-8"
        html = resp.text
        status = resp.status_code
        fetched_at = _utc_now_iso()
        return url, status, html, fetched_at
    except requests.RequestException:
        return url, 0, None, _utc_now_iso()


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def process_pages(pages: Iterable[int]) -> None:
    run_dir, run_started_dt = _prepare_run_dir()
    scrape_run_id = str(uuid4())
    run_started_at = run_started_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    session = requests.Session()

    for page_number in pages:
        url, status, html, fetched_at = fetch_listing_page(session, page_number)
        html_path = run_dir / f"page_pg={page_number}.html"
        if html is not None:
            html_path.write_text(html, encoding="utf-8")

        products: list[dict] = []
        if html:
            try:
                products = parse_products(html, page_number, scrape_run_id)
            except Exception:
                products = []

        meta = {
            "page_number": page_number,
            "url": url,
            "fetched_at_utc": fetched_at,
            "http_status": status,
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
