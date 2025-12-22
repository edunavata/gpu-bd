from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Set

from bs4 import BeautifulSoup


PRODUCT_URL_RE = re.compile(r"-a\d+\.html$")


def extract_product_urls_from_category_html(html_path: Path) -> Set[str]:
    """Extract Geizhals product URLs from a category listing HTML.

    A product URL is identified by ending with '-aXXXX.html'.

    :param html_path: Path to the saved category HTML file.
    :return: Set of absolute product URLs.
    """
    html = html_path.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "lxml")

    product_urls: Set[str] = set()

    for a in soup.find_all("a", href=True):
        href = a["href"]

        if PRODUCT_URL_RE.search(href):
            if href.startswith("http"):
                product_urls.add(href)
            else:
                product_urls.add(f"https://geizhals.de/{href}")

    return product_urls


def write_bronze_discovery_output(
    product_urls: Set[str],
    category_url: str,
    output_dir: Path,
) -> Path:
    """Write a bronze discovery JSON file.

    :param product_urls: Set of discovered product URLs.
    :param category_url: Source category URL.
    :param output_dir: Base bronze directory.
    :return: Path to the written JSON file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "source": "geizhals",
        "entity": "gpu",
        "category_url": category_url,
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "product_count": len(product_urls),
        "product_urls": sorted(product_urls),
    }

    out_path = output_dir / "geizhals_gpu_product_urls.json"
    out_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    return out_path


if __name__ == "__main__":
    # INPUT
    CATEGORY_HTML = Path("data/bronze/geizhals/gpu/2025-12-22/_cat=gra16_512.html")
    CATEGORY_URL = "https://geizhals.de/?cat=gra16_512"
    BRONZE_DIR = Path("data/bronze/geizhals/gpu/2025-12-22")

    CATEGORY_URL = "https://geizhals.de/?cat=gra16_512"

    # OUTPUT
    BRONZE_DIR = Path("data/bronze/geizhals/gpu/discovery")

    product_urls = extract_product_urls_from_category_html(CATEGORY_HTML)
    out_file = write_bronze_discovery_output(product_urls, CATEGORY_URL, BRONZE_DIR)

    print(f"Discovered {len(product_urls)} GPU product pages")
    print(f"Saved to: {out_file}")
