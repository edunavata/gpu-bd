#!/usr/bin/env python3
import argparse
import logging
import subprocess
import sys
import time
from typing import List, Sequence


DEFAULT_PAGES = [1, 2, 3]


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="[%(levelname)s] %(message)s",
    )


def _run_step(cmd: Sequence[str], step_name: str) -> None:
    logging.info("Starting %s", step_name)
    start = time.perf_counter()
    subprocess.run(cmd, check=True)
    elapsed = time.perf_counter() - start
    logging.info("%s completed in %.1fs", step_name, elapsed)


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bronze GPU orchestration pipeline.")
    parser.add_argument(
        "--pages",
        nargs="*",
        type=int,
        default=DEFAULT_PAGES,
        help="Geizhals listing pages to scrape (default: 1 2 3).",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str]) -> int:
    _configure_logging()
    args = _parse_args(argv)
    pages: List[int] = args.pages or DEFAULT_PAGES

    logging.info("Starting Bronze GPU pipeline")

    try:
        geizhals_cmd = [
            sys.executable,
            "-m",
            "src.bronze.gpu.geizhals.listing",
            *[str(p) for p in pages],
        ]
        _run_step(geizhals_cmd, "Step 1: Geizhals listing (pages: {})".format(",".join(map(str, pages))))

        variants_cmd = [
            sys.executable,
            "-m",
            "src.bronze.gpu.variant.pipeline",
        ]
        _run_step(variants_cmd, "Step 2: Variant enrichment pipeline")
    except subprocess.CalledProcessError:
        logging.exception("Fatal error in Bronze GPU pipeline")
        return 1

    logging.info("Bronze GPU pipeline finished successfully")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
