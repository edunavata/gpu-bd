from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional

from src.common.db import _configure_connection
from src.silver.gpu.normalize import NormalizedCandidate, canonical_model_key, normalize


DEFAULT_DB_PATH = Path("db/pcbuilder.db")
DEFAULT_HYPOTHESES_DIR = Path("data/bronze/gpu/hypotheses")

_RESET = "\033[0m"
_RED_BOLD = "\033[1;31m"
_CYAN = "\033[36m"
_BOLD = "\033[1m"
_YELLOW = "\033[33m"
_DIM = "\033[2m"


@dataclass(frozen=True, slots=True)
class MatchAttempt:
    chip_id: Optional[str]
    candidates: list[str]
    match_state: Optional[str]
    vendor_id: Optional[str]
    model_key: Optional[str]
    vram_gb: Optional[int]
    aib_manufacturer: Optional[str] = None


def _canonical_model_key_with_vram(
    model_raw: Optional[str],
    vram_gb: Optional[int],
) -> Optional[str]:
    if not model_raw:
        return None

    model_key = canonical_model_key(model_raw)
    if not model_key:
        return None

    if vram_gb is not None and "gb" not in model_key:
        model_key = f"{model_key} {vram_gb} gb"

    return model_key


def _stable_variant_id(parts: Iterable[Any]) -> str:
    normalized_parts = []
    for part in parts:
        if part is None:
            normalized_parts.append("")
        elif isinstance(part, bool):
            normalized_parts.append("true" if part else "false")
        else:
            normalized_parts.append(str(part).strip().lower())
    digest = hashlib.sha256("|".join(normalized_parts).encode("utf-8")).hexdigest()
    return f"var_{digest}"


def _coerce_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _coerce_int(value: Any) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(round(value))
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _coerce_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _detect_hypotheses_dir() -> Path:
    preferred = DEFAULT_HYPOTHESES_DIR / "perplexity_ai"
    if preferred.is_dir():
        return preferred
    return DEFAULT_HYPOTHESES_DIR


def _get_connection(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    _configure_connection(conn)
    return conn


def _load_chip_index(conn: sqlite3.Connection) -> dict[str, dict[str, list[str]]]:
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            c.chip_id,
            c.vendor_id,
            c.model_name,
            m.vram_gb
        FROM gpu_chip c
        LEFT JOIN gpu_memory m
            ON m.chip_id = c.chip_id
        """
    )

    index: dict[str, dict[str, list[str]]] = {}

    for row in cursor.fetchall():
        chip_id = row["chip_id"]
        vendor_id = row["vendor_id"]
        model_name = row["model_name"]
        vram_gb = row["vram_gb"]

        model_key = canonical_model_key(model_name)
        if not model_key:
            continue

        # 🔑 Regla única: siempre GB en la key
        if "gb" not in model_key and vram_gb is not None:
            model_key = f"{model_key} {vram_gb} gb"

        vendor_map = index.setdefault(vendor_id, {})
        vendor_map.setdefault(model_key, []).append(chip_id)

    cursor.close()
    return index


def _load_chip_details(conn: sqlite3.Connection) -> dict[str, dict[str, str]]:
    cursor = conn.cursor()
    cursor.execute("SELECT chip_id, vendor_id, model_name FROM gpu_chip")
    details: dict[str, dict[str, str]] = {}
    for row in cursor.fetchall():
        chip_id = row["chip_id"]
        if chip_id is None:
            continue
        details[str(chip_id)] = {
            "vendor_id": str(row["vendor_id"]),
            "model_name": str(row["model_name"]),
        }
    cursor.close()
    return details


def _load_memory_map(conn: sqlite3.Connection) -> dict[str, int]:
    cursor = conn.cursor()
    cursor.execute("SELECT chip_id, vram_gb FROM gpu_memory")
    mapping: dict[str, int] = {}
    for row in cursor.fetchall():
        chip_id = row["chip_id"]
        vram_gb = row["vram_gb"]
        if chip_id is None or vram_gb is None:
            continue
        mapping[chip_id] = int(vram_gb)
    cursor.close()
    return mapping


def _iter_hypothesis_files(hypotheses_dir: Path, limit: Optional[int]) -> list[Path]:
    files = sorted(path for path in hypotheses_dir.rglob("*.json") if path.is_file())
    if limit is not None:
        return files[:limit]
    return files


def _normalize_vendor(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    key = str(value).strip().upper()
    if key == "NVIDIA":
        return "NVIDIA"
    if key == "AMD":
        return "AMD"
    return None


def _format_chip_label(
    chip_id: str, chip_details: dict[str, dict[str, str]], vram_map: dict[str, int]
) -> str:
    info = chip_details.get(chip_id)
    if not info:
        return chip_id
    label = f"{info['vendor_id']} {info['model_name']}"
    vram_gb = vram_map.get(chip_id)
    if vram_gb:
        return f"{label} ({vram_gb}GB)"
    return label


def _select_chip_id(
    vendor_id: str,
    model_key: str,
    vram_gb: Optional[int],
    chip_index: dict[str, dict[str, list[str]]],
    vram_map: dict[str, int],
) -> tuple[Optional[str], list[str], Optional[str]]:
    candidates = list(chip_index.get(vendor_id, {}).get(model_key, []))
    if not candidates:
        return None, [], "no_match"
    if vram_gb is None:
        if len(candidates) == 1:
            return candidates[0], candidates, None
        return None, candidates, "ambiguous"
    filtered = [chip_id for chip_id in candidates if vram_map.get(chip_id) == vram_gb]
    if len(filtered) == 1:
        return filtered[0], filtered, None
    if not filtered:
        return None, candidates, "no_match"
    return None, filtered, "ambiguous"


def _attempt_match(
    vendor_id: Optional[str],
    model_raw: Optional[str],
    vram_gb: Optional[int],
    chip_index: dict[str, dict[str, list[str]]],
    vram_map: dict[str, int],
    aib_manufacturer: Optional[str] = None,
) -> MatchAttempt:
    if not vendor_id or not model_raw:
        return MatchAttempt(None, [], "missing", vendor_id, None, vram_gb)
    model_key = canonical_model_key(model_raw)
    if vram_gb is not None and "gb" not in model_key:
        model_key = f"{model_key} {vram_gb} gb"
    if not model_key:
        return MatchAttempt(None, [], "missing", vendor_id, model_key, vram_gb)
    chip_id, candidates, match_state = _select_chip_id(
        vendor_id, model_key, vram_gb, chip_index, vram_map
    )
    return MatchAttempt(
        chip_id,
        candidates,
        match_state,
        vendor_id,
        model_key,
        vram_gb,
        aib_manufacturer,
    )


def try_match_with_normalize(
    payload: dict[str, Any],
    chip_index: dict[str, dict[str, list[str]]],
    vram_map: dict[str, int],
) -> MatchAttempt:
    input_payload = payload.get("input") or {}
    raw_name = input_payload.get("model_name")
    if not isinstance(raw_name, str) or not raw_name.strip():
        return MatchAttempt(None, [], "missing", None, None, None)
    bronze_record = {"product_name_raw": raw_name}
    normalized: NormalizedCandidate = normalize(bronze_record)
    return _attempt_match(
        _normalize_vendor(normalized.vendor_hint),
        normalized.model_name_hint,
        _coerce_int(normalized.vram_gb_hint),
        chip_index,
        vram_map,
        normalized.aib_manufacturer_hint,
    )


def try_match_with_extraction(
    payload: dict[str, Any],
    chip_index: dict[str, dict[str, list[str]]],
    vram_map: dict[str, int],
) -> MatchAttempt:
    extraction = payload.get("extraction") or {}
    return _attempt_match(
        _normalize_vendor(extraction.get("chipset_manufacturer")),
        _coerce_str(extraction.get("chipset_model")),
        _coerce_int(extraction.get("vram_gb")),
        chip_index,
        vram_map,
        _coerce_str(extraction.get("aib_manufacturer")),
    )


def _clean_dimensions(
    length_mm: Optional[int], width_slots: Optional[float], height_mm: Optional[int]
) -> tuple[Optional[int], Optional[float], Optional[int]]:
    if length_mm is not None and length_mm <= 0:
        length_mm = None
    if width_slots is not None and not (2.0 <= width_slots <= 4.0):
        width_slots = None
    if height_mm is not None and height_mm <= 0:
        height_mm = None
    return length_mm, width_slots, height_mm


def _clean_non_negative(value: Optional[int]) -> Optional[int]:
    if value is None:
        return None
    if value < 0:
        return None
    return value


def _print(message: str, verbose: bool, force: bool = False) -> None:
    if force or verbose:
        print(message)


def _print_with_details(
    header: str, details: Iterable[str], verbose: bool, force: bool = False
) -> None:
    if not (force or verbose):
        return
    print(header)
    for line in details:
        print(f"  {line}")


def _print_skip_report(
    path: Path,
    payload: dict[str, Any],
    extraction: dict[str, Any],
    vendor_id: Optional[str],
    model_raw: Optional[str],
    model_key: Optional[str],
    vram_gb: Optional[int],
    candidates: list[str],
    filtered_candidates: list[str],
    chip_index: dict[str, dict[str, list[str]]],
    vram_map: dict[str, int],
    reason: str,
    explanation: str,
    verbose: bool,
    force: bool = False,
) -> None:
    if not (force or verbose):
        return
    vendor_present = bool(vendor_id and vendor_id in chip_index)
    json_block = json.dumps(payload, indent=2, ensure_ascii=False)

    print("-" * 40)
    print(f"{_RED_BOLD}SKIP {reason} {path}{_RESET}")
    print("-" * 40)
    print()

    print(f"{_CYAN}<Input Section>{_RESET}")
    print(f"  {_BOLD}hypothesis_type={_RESET}{payload.get('hypothesis_type')!r}")
    print(f"  {_BOLD}chipset_manufacturer={_RESET}{extraction.get('chipset_manufacturer')!r}")
    print(f"  {_BOLD}chipset_model={_RESET}{extraction.get('chipset_model')!r}")
    print(f"  {_BOLD}vram_gb={_RESET}{extraction.get('vram_gb')!r}")
    print(f"  {_BOLD}aib_manufacturer={_RESET}{extraction.get('aib_manufacturer')!r}")
    print(_RESET)

    print(f"{_CYAN}<Normalization Section>{_RESET}")
    print(f"  {_BOLD}vendor_id={_RESET}{vendor_id!r}")
    print(f"  {_BOLD}model_raw={_RESET}{model_raw!r}")
    print(f"  {_BOLD}canonical_model_key={_RESET}{model_key!r}")
    print(f"  {_BOLD}vram_gb={_RESET}{vram_gb!r}")
    print(_RESET)

    print(f"{_CYAN}<Chip index Section>{_RESET}")
    print(f"  {_BOLD}vendor_present={_RESET}{vendor_present}")
    print(
        f"  {_BOLD}available_model_keys_sample={_RESET}"
        f"{_sample_model_keys(vendor_id, chip_index)}"
    )
    print(f"  {_BOLD}candidates={_RESET}{candidates}")
    print(_RESET)

    print(f"{_CYAN}<VRAM disambiguation Section>{_RESET}")
    print(f"  {_BOLD}vram_filter={_RESET}{vram_gb!r}")
    print(
        f"  {_BOLD}candidate_vram_map={_RESET}"
        f"{_format_candidate_vram(candidates, vram_map)}"
    )
    print(f"  {_BOLD}filtered_candidates={_RESET}{filtered_candidates}")
    print(_RESET)

    print(f"{_CYAN}<Decision Section>{_RESET}")
    print(f"  {_BOLD}reason={_RESET}{_YELLOW}{reason}{_RESET}")
    print(f"  {_BOLD}explanation={_RESET}{_YELLOW}{explanation}{_RESET}")
    print(_RESET)

    print(f"{_CYAN}<Original JSON Section>{_RESET}")
    print(f"{_DIM}{json_block}{_RESET}")


def _sample_model_keys(
    vendor_id: Optional[str], chip_index: dict[str, dict[str, list[str]]]
) -> list[str]:
    if not vendor_id:
        return []
    vendor_map = chip_index.get(vendor_id)
    if not vendor_map:
        return []
    return sorted(vendor_map.keys())[:10]


def _format_candidate_vram(
    candidates: list[str], vram_map: dict[str, int]
) -> list[str]:
    return [f"{chip_id}={vram_map.get(chip_id)}" for chip_id in candidates]


def _compute_candidate_lists(
    vendor_id: Optional[str],
    model_key: Optional[str],
    vram_gb: Optional[int],
    chip_index: dict[str, dict[str, list[str]]],
    vram_map: dict[str, int],
) -> tuple[list[str], list[str]]:
    if not vendor_id or not model_key:
        return [], []
    candidates = list(chip_index.get(vendor_id, {}).get(model_key, []))
    if vram_gb is None:
        return candidates, candidates
    filtered = [chip_id for chip_id in candidates if vram_map.get(chip_id) == vram_gb]
    return candidates, filtered


def _build_skip_diagnostics(
    payload: dict[str, Any],
    extraction: dict[str, Any],
    vendor_id: Optional[str],
    model_raw: Optional[str],
    model_key: Optional[str],
    vram_gb: Optional[int],
    candidates: list[str],
    filtered_candidates: list[str],
    chip_index: dict[str, dict[str, list[str]]],
    vram_map: dict[str, int],
    reason: str,
    explanation: str,
) -> list[str]:
    hypothesis_type = payload.get("hypothesis_type")
    vendor_present = bool(vendor_id and vendor_id in chip_index)
    return [
        "Input:",
        f"  hypothesis_type={hypothesis_type!r}",
        f"  chipset_manufacturer={extraction.get('chipset_manufacturer')!r}",
        f"  chipset_model={extraction.get('chipset_model')!r}",
        f"  vram_gb={extraction.get('vram_gb')!r}",
        f"  aib_manufacturer={extraction.get('aib_manufacturer')!r}",
        "Normalization:",
        f"  vendor_id={vendor_id!r}",
        f"  model_raw={model_raw!r}",
        f"  canonical_model_key={model_key!r}",
        f"  vram_gb={vram_gb!r}",
        "Chip index:",
        f"  vendor_present={vendor_present}",
        f"  available_model_keys_sample={_sample_model_keys(vendor_id, chip_index)}",
        f"  candidates={candidates}",
        "VRAM disambiguation:",
        f"  vram_filter={vram_gb!r}",
        f"  candidate_vram_map={_format_candidate_vram(candidates, vram_map)}",
        f"  filtered_candidates={filtered_candidates}",
        "Decision:",
        f"  reason={reason}",
        f"  explanation={explanation}",
    ]


def ingest_variants(
    db_path: Path,
    hypotheses_dir: Path,
    dry_run: bool,
    limit: Optional[int],
    verbose: bool,
    only_skipped: bool,
) -> int:
    conn = _get_connection(db_path)
    chip_index = _load_chip_index(conn)
    vram_map = _load_memory_map(conn)
    chip_details = _load_chip_details(conn)

    cursor = conn.cursor()

    counters = {
        "files_scanned": 0,
        "variants_inserted": 0,
        "skipped_missing_fields": 0,
        "skipped_no_chip_match": 0,
        "skipped_ambiguous_chip": 0,
        "skipped_duplicate": 0,
        "skipped_wrong_type": 0,
        "errors": 0,
    }

    files = _iter_hypothesis_files(hypotheses_dir, limit)
    for path in files:
        counters["files_scanned"] += 1
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            counters["errors"] += 1
            _print(f"ERROR read {path}: {exc}", verbose, force=True)
            continue

        if payload.get("hypothesis_type") != "gpu_variant":
            counters["skipped_wrong_type"] += 1
            extraction = payload.get("extraction") or {}
            vendor_id = _normalize_vendor(extraction.get("chipset_manufacturer"))
            model_raw = _coerce_str(extraction.get("chipset_model"))
            model_key = canonical_model_key(model_raw) if model_raw else None
            vram_gb = _coerce_int(extraction.get("vram_gb"))
            candidates, filtered = _compute_candidate_lists(
                vendor_id, model_key, vram_gb, chip_index, vram_map
            )
            _print_skip_report(
                path,
                payload,
                extraction,
                vendor_id,
                model_raw,
                model_key,
                vram_gb,
                candidates,
                filtered,
                chip_index,
                vram_map,
                "wrong_hypothesis_type",
                "Hypothesis type is not gpu_variant.",
                verbose,
                force=dry_run,
            )
            continue

        extraction = payload.get("extraction") or {}

        normalize_attempt = try_match_with_normalize(payload, chip_index, vram_map)
        extraction_attempt = extraction_attempt = try_match_with_extraction(
            payload, chip_index, vram_map
        )
        if normalize_attempt.chip_id:
            match_attempt = normalize_attempt
            match_source = "normalize"
        else:

            match_attempt = extraction_attempt
            match_source = "extraction"

        chip_id = match_attempt.chip_id
        vendor_id = match_attempt.vendor_id
        model_key = match_attempt.model_key
        vram_gb = match_attempt.vram_gb
        aib_manufacturer = (
            normalize_attempt.aib_manufacturer
            if normalize_attempt.aib_manufacturer
            else extraction_attempt.aib_manufacturer
        )

        if not aib_manufacturer:
            counters["skipped_missing_fields"] += 1
            model_raw = _coerce_str(extraction.get("chipset_model"))
            model_key = canonical_model_key(model_raw) if model_raw else None
            vram_gb = _coerce_int(extraction.get("vram_gb"))
            vendor_id = _normalize_vendor(extraction.get("chipset_manufacturer"))
            candidates, filtered = _compute_candidate_lists(
                vendor_id, model_key, vram_gb, chip_index, vram_map
            )
            _print_skip_report(
                path,
                payload,
                extraction,
                vendor_id,
                model_raw,
                model_key,
                vram_gb,
                candidates,
                filtered,
                chip_index,
                vram_map,
                "missing_fields",
                "Required fields for matching are missing.",
                verbose,
                force=dry_run,
            )
            continue

        if chip_id is None:
            if match_attempt.match_state == "missing":
                counters["skipped_missing_fields"] += 1
                reason = "missing_fields"
                explanation = "Required fields for matching are missing."
            elif match_attempt.match_state == "ambiguous":
                counters["skipped_ambiguous_chip"] += 1
                reason = "ambiguous_chip_match"
                explanation = "Multiple chips match the vendor/model/VRAM criteria."
            else:
                counters["skipped_no_chip_match"] += 1
                reason = "no_chip_match"
                explanation = "No chip matches the vendor/model/VRAM criteria."
            model_raw = _coerce_str(extraction.get("chipset_model"))
            model_key = canonical_model_key(model_raw) if model_raw else None
            vram_gb = _coerce_int(extraction.get("vram_gb"))
            vendor_id = _normalize_vendor(extraction.get("chipset_manufacturer"))
            candidates, filtered = _compute_candidate_lists(
                vendor_id, model_key, vram_gb, chip_index, vram_map
            )
            _print_skip_report(
                path,
                payload,
                extraction,
                vendor_id,
                model_raw,
                model_key,
                vram_gb,
                candidates,
                filtered,
                chip_index,
                vram_map,
                reason,
                explanation,
                verbose,
                force=dry_run,
            )
            continue

        model_suffix = _coerce_str(
            extraction.get("aib_model_suffix") or extraction.get("model_suffix")
        )
        part_number = _coerce_str(extraction.get("part_number"))
        variant_id = _stable_variant_id(
            [vendor_id, model_key, vram_gb, aib_manufacturer, model_suffix, part_number]
        )

        factory_boost_mhz = _coerce_int(extraction.get("factory_boost_mhz"))
        length_mm = _coerce_int(extraction.get("length_mm"))
        width_slots = _coerce_float(extraction.get("width_slots"))
        height_mm = _coerce_int(extraction.get("height_mm"))
        length_mm, width_slots, height_mm = _clean_dimensions(
            length_mm, width_slots, height_mm
        )

        cooling_type = _coerce_str(extraction.get("cooling_type"))
        if cooling_type not in {None, "Air", "Liquid", "Hybrid"}:
            cooling_type = None

        fan_count = _clean_non_negative(_coerce_int(extraction.get("fan_count")))
        displayport_count = _clean_non_negative(
            _coerce_int(extraction.get("displayport_count"))
        )
        hdmi_count = _clean_non_negative(_coerce_int(extraction.get("hdmi_count")))

        displayport_version = _coerce_str(extraction.get("displayport_version"))
        hdmi_version = _coerce_str(extraction.get("hdmi_version"))
        power_connectors = _coerce_str(extraction.get("power_connectors"))
        warranty_years = _clean_non_negative(
            _coerce_int(extraction.get("warranty_years"))
        )

        if dry_run:
            cursor.execute(
                "SELECT 1 FROM gpu_variant WHERE variant_id = ?",
                (variant_id,),
            )
            if cursor.fetchone():
                counters["skipped_duplicate"] += 1
            else:
                counters["variants_inserted"] += 1
                if not only_skipped:
                    _print_with_details(
                        f"DRY RUN insert {path}",
                        [
                            f"match_source={match_source}",
                            f'resolved_chip="{_format_chip_label(chip_id, chip_details, vram_map)}"',
                            f"chip_id={chip_id}",
                            f"variant_id={variant_id}",
                        ],
                        verbose,
                        force=True,
                    )
            continue

        try:
            cursor.execute(
                """
                INSERT INTO gpu_variant (
                    variant_id,
                    chip_id,
                    aib_manufacturer,
                    model_suffix,
                    factory_boost_mhz,
                    length_mm,
                    width_slots,
                    height_mm,
                    power_connectors,
                    cooling_type,
                    fan_count,
                    displayport_count,
                    displayport_version,
                    hdmi_count,
                    hdmi_version,
                    warranty_years
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(variant_id) DO NOTHING
                """,
                (
                    variant_id,
                    chip_id,
                    aib_manufacturer,
                    model_suffix,
                    factory_boost_mhz,
                    length_mm,
                    width_slots,
                    height_mm,
                    power_connectors,
                    cooling_type,
                    fan_count,
                    displayport_count,
                    displayport_version,
                    hdmi_count,
                    hdmi_version,
                    warranty_years,
                ),
            )
        except sqlite3.Error as exc:
            counters["errors"] += 1
            _print(f"ERROR insert {path}: {exc}", verbose, force=True)
            continue

        if cursor.rowcount == 0:
            counters["skipped_duplicate"] += 1
        else:
            counters["variants_inserted"] += 1
            if not only_skipped:
                _print_with_details(
                    f"INSERT {path}",
                    [
                        f"match_source={match_source}",
                        f'resolved_chip="{_format_chip_label(chip_id, chip_details, vram_map)}"',
                        f"chip_id={chip_id}",
                        f"variant_id={variant_id}",
                    ],
                    verbose,
                    force=False,
                )

    if not dry_run:
        conn.commit()
    cursor.close()
    conn.close()

    print("Summary")
    for key in (
        "files_scanned",
        "variants_inserted",
        "skipped_missing_fields",
        "skipped_no_chip_match",
        "skipped_ambiguous_chip",
        "skipped_duplicate",
        "errors",
    ):
        print(f"{key}: {counters[key]}")
    if counters["skipped_wrong_type"]:
        print(f"skipped_wrong_type: {counters['skipped_wrong_type']}")

    return 0 if counters["errors"] == 0 else 1


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest GPU variant hypotheses into silver gpu_variant table."
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        help="SQLite database path (default: db/pcbuilder.db)",
    )
    parser.add_argument(
        "--hypotheses-dir",
        type=Path,
        default=None,
        help="Directory containing hypothesis JSON files",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned inserts without writing to the database",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Process only the first N hypothesis files",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    parser.add_argument(
        "--only-skipped",
        action="store_true",
        help="Print only skipped records and suppress successful inserts",
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    hypotheses_dir = args.hypotheses_dir or _detect_hypotheses_dir()
    if not hypotheses_dir.exists():
        print(f"Hypotheses directory not found: {hypotheses_dir}")
        return 1
    return ingest_variants(
        db_path=args.db_path,
        hypotheses_dir=hypotheses_dir,
        dry_run=args.dry_run,
        limit=args.limit,
        verbose=args.verbose,
        only_skipped=args.only_skipped,
    )


if __name__ == "__main__":
    raise SystemExit(main())
