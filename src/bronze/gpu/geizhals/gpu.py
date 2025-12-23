from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional
import random

import requests


@dataclass(frozen=True)
class FetchResult:
    """Result of a single fetch operation.

    :param url: Product page URL.
    :param status_code: HTTP status code.
    :param saved_html_path: Path where HTML was saved (if any).
    :param saved_meta_path: Path where metadata JSON was saved (if any).
    """

    url: str
    status_code: int
    saved_html_path: Optional[Path]
    saved_meta_path: Optional[Path]


def _utc_now_iso() -> str:
    """Return current UTC time as ISO8601 string."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def fetch_product_pages_to_bronze(
    product_urls: Iterable[str],
    bronze_dir: Path,
    session: Optional[requests.Session] = None,
    min_sleep_s: float = 3.0,
    max_sleep_s: float = 8.0,
    timeout_s: float = 25.0,
) -> list[FetchResult]:
    """Fetch Geizhals product pages (HTML) and store them in the bronze layer.

    :param product_urls: Iterable of product page URLs.
    :param bronze_dir: Base directory to store bronze artifacts.
    :param session: Optional requests session for connection reuse.
    :param min_sleep_s: Minimum delay between requests (seconds).
    :param max_sleep_s: Maximum delay between requests (seconds).
    :param timeout_s: Request timeout (seconds).
    :return: List of FetchResult.
    """
    bronze_dir.mkdir(parents=True, exist_ok=True)
    s = session or requests.Session()

    headers = {
        # Keep UA honest. Avoid pretending to be Chrome if you are not.
        "User-Agent": "pcbuilder-research/0.1 (contact: your-email@example.com)",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "de,en;q=0.8,es;q=0.6",
    }

    results: list[FetchResult] = []
    run_date = datetime.now().strftime("%Y-%m-%d")
    day_dir = bronze_dir / run_date
    day_dir.mkdir(parents=True, exist_ok=True)

    for url in product_urls:
        ts = _utc_now_iso()
        safe_id = url.rstrip("/").split("/")[-1].replace("?", "_").replace("&", "_")
        html_path = day_dir / f"{safe_id}.html"
        meta_path = day_dir / f"{safe_id}.meta.json"

        try:
            resp = s.get(url, headers=headers, timeout=timeout_s)
            status = resp.status_code

            saved_html = None
            saved_meta = None

            if status == 200 and resp.text:
                html_path.write_text(resp.text, encoding="utf-8")
                meta = {
                    "url": url,
                    "fetched_at_utc": ts,
                    "status_code": status,
                    "content_length": len(resp.content),
                }
                meta_path.write_text(
                    json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                saved_html = html_path
                saved_meta = meta_path

            results.append(
                FetchResult(
                    url=url,
                    status_code=status,
                    saved_html_path=saved_html,
                    saved_meta_path=saved_meta,
                )
            )

        except requests.RequestException:
            # Store failure as a result; do not crash the run.
            results.append(
                FetchResult(
                    url=url, status_code=0, saved_html_path=None, saved_meta_path=None
                )
            )

        # Polite throttling
        time.sleep(random.uniform(min_sleep_s, max_sleep_s))

    return results


if __name__ == "__main__":
    # Example: start with a small curated list of product pages
    urls = [
        "https://geizhals.de/?cat=gra16_512",
    ]

    out_dir = Path("data/bronze/gpu/marketplace/geizhals")
    res = fetch_product_pages_to_bronze(urls, out_dir)

    print(f"Fetched: {len(res)} pages")
    print("Statuses:", {r.status_code for r in res})
