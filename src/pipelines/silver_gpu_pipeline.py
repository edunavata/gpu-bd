#!/usr/bin/env python3
import argparse
import logging
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Sequence


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
    parser = argparse.ArgumentParser(description="Silver GPU orchestration pipeline.")
    parser.add_argument("--db-path", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args(argv)


def _build_common_flags(args: argparse.Namespace) -> List[str]:
    flags: List[str] = []
    if args.db_path is not None:
        flags.extend(["--db-path", str(args.db_path)])
    if args.dry_run:
        flags.append("--dry-run")
    if args.limit is not None:
        flags.extend(["--limit", str(args.limit)])
    if args.verbose:
        flags.append("--verbose")
    return flags


def main(argv: Sequence[str]) -> int:
    _configure_logging()
    args = _parse_args(argv)
    common_flags = _build_common_flags(args)

    logging.info("Starting Silver GPU pipeline")

    try:
        ingest_variants_cmd = [
            sys.executable,
            "-m",
            "src.silver.gpu.ingest_variants_from_hypotheses",
            *common_flags,
        ]
        _run_step(ingest_variants_cmd, "Step 1: Ingest GPU variants from hypotheses")

        ingest_observations_cmd = [
            sys.executable,
            "-m",
            "src.silver.gpu.ingest_market_observations",
            *common_flags,
        ]
        _run_step(ingest_observations_cmd, "Step 2: Ingest GPU market observations")
    except subprocess.CalledProcessError:
        logging.exception("Fatal error in Silver GPU pipeline")
        return 1

    logging.info("Silver GPU pipeline finished successfully")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
