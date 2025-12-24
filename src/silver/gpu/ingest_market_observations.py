from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional

# Importamos la lógica determinista EXACTA del script de variantes.
# Asumimos que el otro script está accesible como módulo o en el PYTHONPATH.
try:
    from src.silver.gpu.ingest_variants_from_hypotheses import (
        _coerce_float,
        _coerce_str,
        _get_connection,
        _load_chip_index,
        _load_memory_map,
        _stable_variant_id,
        try_match_with_extraction,
        try_match_with_normalize,
    )
except ImportError:
    # Fallback para desarrollo local si no está instalado como paquete
    sys.path.append(str(Path.cwd()))
    from src.silver.gpu.ingest_variants_from_hypotheses import (
        _coerce_float,
        _coerce_str,
        _get_connection,
        _load_chip_index,
        _load_memory_map,
        _stable_variant_id,
        try_match_with_extraction,
        try_match_with_normalize,
    )

DEFAULT_DB_PATH = Path("db/pcbuilder.db")
# Usamos resolve() para evitar ambiguedades entre rutas relativas/absolutas
BRONZE_GPU_ROOT = Path("data/bronze/gpu").resolve()
DEFAULT_MARKETPLACE_DIR = BRONZE_GPU_ROOT / "marketplace"
DEFAULT_INDEX_DIR = BRONZE_GPU_ROOT / "indexes" / "observed_product"

ALLOWED_STOCK_STATUS = {
    "in_stock",
    "low_stock",
    "preorder",
    "out_of_stock",
    "discontinued",
}


@dataclass(frozen=True, slots=True)
class IndexEntry:
    index_path: Path
    hypotheses: list[str]
    product_url: Optional[str]
    normalized_name: Optional[str]


def _stable_observation_id(parts: Iterable[Any]) -> str:
    """Genera un ID determinista para la observación de mercado."""
    normalized_parts = []
    for part in parts:
        if part is None:
            normalized_parts.append("")
        elif isinstance(part, bool):
            normalized_parts.append("true" if part else "false")
        else:
            normalized_parts.append(str(part).strip().lower())
    digest = hashlib.sha256("|".join(normalized_parts).encode("utf-8")).hexdigest()
    return f"obs_{digest}"


def _iter_marketplace_files(marketplace_dir: Path) -> list[Path]:
    """Encuentra todos los archivos de productos escrapeados."""
    # Usamos resolve() para asegurar que devolvemos rutas absolutas
    return sorted(
        [
            p.resolve()
            for p in marketplace_dir.glob("**/runs/**/page_pg=*.products.json")
        ]
    )


def _load_marketplace_file(path: Path) -> Optional[list[dict[str, Any]]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, list):
        return None
    return [item for item in payload if isinstance(item, dict)]


def _load_index_map(
    index_dir: Path, verbose: bool
) -> tuple[dict[str, list[IndexEntry]], int]:
    """
    Carga el mapa inverso: Observación (string) -> Entrada de Índice.
    Este es el puente crítico.
    """
    index_map: dict[str, list[IndexEntry]] = {}
    errors = 0
    scanned_files = 0
    total_references = 0

    if not index_dir.exists():
        return {}, 0

    for path in sorted(index_dir.glob("*.json")):
        scanned_files += 1
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors += 1
            _print(f"ERROR read index {path}: {exc}", verbose, force=True)
            continue

        marketplace_obs = payload.get("marketplace_observations")
        if not isinstance(marketplace_obs, list):
            continue

        hypotheses = payload.get("hypotheses") or []
        if not isinstance(hypotheses, list):
            continue

        product_url = _coerce_str(payload.get("product_url"))
        normalized_name = _coerce_str(payload.get("normalized_name"))
        entry = IndexEntry(
            index_path=path,
            hypotheses=hypotheses,
            product_url=product_url,
            normalized_name=normalized_name,
        )

        for obs_ref in marketplace_obs:
            if not isinstance(obs_ref, str) or not obs_ref.strip():
                continue
            # obs_ref suele ser algo como "marketplace/geizhals/..."
            index_map.setdefault(obs_ref, []).append(entry)
            total_references += 1

    if verbose:
        print(
            f"Index Load Stats: Scanned {scanned_files} files, loaded {total_references} references."
        )

    return index_map, errors


def _get_table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = {row[1] for row in cursor.fetchall()}
    cursor.close()
    return columns


def _print(message: str, verbose: bool, force: bool = False) -> None:
    if force or verbose:
        print(message)


def _print_skip(
    observation_ref: str,
    reason: str,
    detail: str,
    verbose: bool,
) -> None:
    # Formato estándar de reporte de Skip
    print(f"SKIP {observation_ref} reason={reason} detail={detail}")
    if verbose:
        print(f"  -> {detail}")


def _should_debug_skip(
    reason: str, debug_skips: bool, debug_skips_only_errors: bool
) -> bool:
    if not debug_skips:
        return False
    if debug_skips_only_errors and reason == "skipped_duplicate":
        return False
    return True


def _format_attempt(value: Optional[Any]) -> dict[str, Optional[Any]]:
    if value is None:
        return {
            "match_state": "unavailable",
            "vendor_id": None,
            "model_key": None,
            "vram_gb": None,
            "chip_id": None,
            "aib_manufacturer": None,
        }
    return {
        "match_state": getattr(value, "match_state", None),
        "vendor_id": getattr(value, "vendor_id", None),
        "model_key": getattr(value, "model_key", None),
        "vram_gb": getattr(value, "vram_gb", None),
        "chip_id": getattr(value, "chip_id", None),
        "aib_manufacturer": getattr(value, "aib_manufacturer", None),
    }


def _find_index_diagnostics(
    index_dir: Path,
    product_url: Optional[str],
    normalized_name: Optional[str],
    limit: int = 5,
) -> tuple[list[Path], list[Path]]:
    if not product_url and not normalized_name:
        return [], []
    url_matches: list[Path] = []
    name_matches: list[Path] = []
    for path in sorted(index_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if product_url and _coerce_str(payload.get("product_url")) == product_url:
            url_matches.append(path)
        if (
            normalized_name
            and _coerce_str(payload.get("normalized_name")) == normalized_name
        ):
            name_matches.append(path)
        if len(url_matches) >= limit and len(name_matches) >= limit:
            break
    return url_matches, name_matches


def _print_skip_debug(
    *,
    observation_ref: str,
    record: dict[str, Any],
    index_entries: Optional[list[IndexEntry]],
    index_entry: Optional[IndexEntry],
    hypothesis_path: Optional[Path],
    normalize_attempt: Optional[Any],
    extraction_attempt: Optional[Any],
    variant_parts: Optional[dict[str, Any]],
    variant_id: Optional[str],
    variant_exists: Optional[bool],
    index_dir: Path,
    debug_skips: bool,
    debug_skips_only_errors: bool,
    reason: str,
) -> None:
    if not _should_debug_skip(reason, debug_skips, debug_skips_only_errors):
        return

    product_name_raw = _coerce_str(record.get("product_name_raw"))
    product_url = _coerce_str(record.get("product_url"))
    normalized_name = _coerce_str(record.get("normalized_name"))

    index_entry_count = len(index_entries) if index_entries else 0
    hypotheses_count = len(index_entry.hypotheses) if index_entry else 0
    index_path = index_entry.index_path if index_entry else None

    print("DEBUG:")
    print(f"  observation_ref: {observation_ref}")
    print(f"  relative_marketplace_path: {observation_ref.split('#')[0]}")
    print(f"  product_name_raw: {product_name_raw!r}")
    print(f"  product_url: {product_url!r}")
    print(f"  index_entry_path: {str(index_path) if index_path else None}")
    print(f"  hypothesis_path: {str(hypothesis_path) if hypothesis_path else None}")
    print(f"  index_lookup: {'FOUND' if index_entry else 'NOT FOUND'}")
    print(f"  index_entry_count: {index_entry_count}")
    print(f"  hypotheses_count: {hypotheses_count}")
    if index_entry:
        print(f"  index_normalized_name: {index_entry.normalized_name!r}")
        print(f"  index_product_url: {index_entry.product_url!r}")

    normalize_info = _format_attempt(normalize_attempt)
    extraction_info = _format_attempt(extraction_attempt)

    print("  normalize_attempt:")
    print(f"    match_state: {normalize_info['match_state']!r}")
    print(f"    vendor_id: {normalize_info['vendor_id']!r}")
    print(f"    model_key: {normalize_info['model_key']!r}")
    print(f"    vram_gb: {normalize_info['vram_gb']!r}")
    print(f"    chip_id: {normalize_info['chip_id']!r}")
    print(f"    aib_manufacturer: {normalize_info['aib_manufacturer']!r}")

    print("  extraction_attempt:")
    print(f"    match_state: {extraction_info['match_state']!r}")
    print(f"    vendor_id: {extraction_info['vendor_id']!r}")
    print(f"    model_key: {extraction_info['model_key']!r}")
    print(f"    vram_gb: {extraction_info['vram_gb']!r}")
    print(f"    chip_id: {extraction_info['chip_id']!r}")
    print(f"    aib_manufacturer: {extraction_info['aib_manufacturer']!r}")

    if reason == "no_index_entry":
        url_matches, name_matches = _find_index_diagnostics(
            index_dir=index_dir,
            product_url=product_url,
            normalized_name=normalized_name,
        )
        print(f"  index_hint_product_url_matches: {[str(p) for p in url_matches]}")
        print(f"  index_hint_normalized_name_matches: {[str(p) for p in name_matches]}")

    if variant_parts is not None:
        print("  variant_parts:")
        print(f"    vendor_id: {variant_parts.get('vendor_id')!r}")
        print(f"    model_key: {variant_parts.get('model_key')!r}")
        print(f"    vram_gb: {variant_parts.get('vram_gb')!r}")
        print(f"    aib_manufacturer: {variant_parts.get('aib_manufacturer')!r}")
        print(f"    model_suffix: {variant_parts.get('model_suffix')!r}")
        print(f"    part_number: {variant_parts.get('part_number')!r}")
        print(f"  variant_id: {variant_id!r}")
        print(f"  variant_exists: {variant_exists!r}")


def _build_variant_parts_for_debug(
    vendor_id: Optional[str],
    model_key: Optional[str],
    vram_gb: Optional[int],
    aib_manufacturer: Optional[str],
    extraction: dict[str, Any],
) -> dict[str, Any]:
    model_suffix = _coerce_str(
        extraction.get("aib_model_suffix") or extraction.get("model_suffix")
    )
    part_number = _coerce_str(extraction.get("part_number"))
    return {
        "vendor_id": vendor_id,
        "model_key": model_key,
        "vram_gb": vram_gb,
        "aib_manufacturer": aib_manufacturer,
        "model_suffix": model_suffix,
        "part_number": part_number,
    }


def ingest_market_observations(
    db_path: Path,
    marketplace_dir: Path,
    index_dir: Path,
    dry_run: bool,
    limit: Optional[int],
    verbose: bool,
    debug_skips: bool,
    debug_skips_only_errors: bool,
) -> int:
    conn = _get_connection(db_path)

    # Cargamos LOS MISMOS índices que usa el script de variantes
    chip_index = _load_chip_index(conn)
    vram_map = _load_memory_map(conn)

    table_columns = _get_table_columns(conn, "gpu_market_observation")
    include_currency = "currency" in table_columns

    debug_skips = debug_skips or debug_skips_only_errors

    index_errors = 0

    cursor = conn.cursor()

    counters = {
        "observations_scanned": 0,
        "observations_inserted": 0,
        "skipped_no_index": 0,
        "skipped_ambiguous_index": 0,
        "skipped_no_hypothesis": 0,
        "skipped_ambiguous_hypothesis": 0,
        "skipped_missing_hypothesis": 0,
        "skipped_missing_fields": 0,
        "skipped_no_chip_match": 0,
        "skipped_ambiguous_chip": 0,
        "skipped_invalid_stock_status": 0,
        "skipped_invalid_price": 0,
        "skipped_duplicate": 0,
        "errors": index_errors,
    }

    # Aseguramos ruta absoluta para marketplace_dir para evitar conflictos con relative_to
    marketplace_dir = marketplace_dir.resolve()
    files = _iter_marketplace_files(marketplace_dir)

    _print(f"Found {len(files)} marketplace files to scan.", verbose)

    for path in files:
        if limit is not None and counters["observations_scanned"] >= limit:
            break

        records = _load_marketplace_file(path)
        if records is None:
            counters["errors"] += 1
            _print(f"ERROR read {path}", verbose, force=True)
            continue

        # CALCULO CRÍTICO DE LA RUTA RELATIVA
        # Debe coincidir exactamente con como se guardó en el JSON de índice.
        # El JSON de índice guarda: "marketplace/geizhals/..." (relativo a BRONZE_GPU_ROOT)
        try:
            relative_path = path.relative_to(BRONZE_GPU_ROOT).as_posix()
        except ValueError:
            # Esto pasa si BRONZE_GPU_ROOT no es parte del path del archivo
            _print(
                f"ERROR path mismatch: {path} is not inside {BRONZE_GPU_ROOT}",
                verbose,
                force=True,
            )
            counters["errors"] += 1
            continue

        for index, record in enumerate(records):
            if limit is not None and counters["observations_scanned"] >= limit:
                break

            counters["observations_scanned"] += 1
            # Esta referencia es la llave para buscar en index_map
            observation_ref = f"{relative_path}#{index}"

            # 1. BUSCAR EL ENLACE EN EL ÍNDICE
            product_url_lookup = _coerce_str(record.get("product_url"))
            url_hash = (
                hashlib.sha256(product_url_lookup.encode("utf-8")).hexdigest()
                if product_url_lookup
                else None
            )
            index_path = index_dir / f"{url_hash}.json" if url_hash else None
            index_payload = None
            index_entries = None

            if index_path and index_path.exists():
                try:
                    index_payload = json.loads(index_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as exc:
                    counters["errors"] += 1
                    _print(f"ERROR read index {index_path}: {exc}", verbose, force=True)
                    continue

            if index_payload is not None:
                hypotheses = index_payload.get("hypotheses") or []
                if not isinstance(hypotheses, list):
                    hypotheses = []
                index_entries = [
                    IndexEntry(
                        index_path=index_path,
                        hypotheses=hypotheses,
                        product_url=_coerce_str(index_payload.get("product_url")),
                        normalized_name=_coerce_str(index_payload.get("normalized_name")),
                    )
                ]

            if not index_entries:
                counters["skipped_no_index"] += 1
                # Este error es el que veías. Significa que ningún archivo en data/bronze/gpu/indexes
                # contiene la cadena exacta 'observation_ref' en su lista 'marketplace_observations'.
                _print_skip(
                    observation_ref,
                    "no_index_entry",
                    "No observed_product index entry found. Has the indexer run for this file?",
                    verbose,
                )
                _print_skip_debug(
                    observation_ref=observation_ref,
                    record=record,
                    index_entries=None,
                    index_entry=None,
                    hypothesis_path=None,
                    normalize_attempt=None,
                    extraction_attempt=None,
                    variant_parts=None,
                    variant_id=None,
                    variant_exists=None,
                    index_dir=index_dir,
                    debug_skips=debug_skips,
                    debug_skips_only_errors=debug_skips_only_errors,
                    reason="no_index_entry",
                )
                continue

            if len(index_entries) > 1:
                counters["skipped_ambiguous_index"] += 1
                _print_skip(
                    observation_ref,
                    "ambiguous_index_entry",
                    "Multiple index entries reference this observation.",
                    verbose,
                )
                _print_skip_debug(
                    observation_ref=observation_ref,
                    record=record,
                    index_entries=index_entries,
                    index_entry=None,
                    hypothesis_path=None,
                    normalize_attempt=None,
                    extraction_attempt=None,
                    variant_parts=None,
                    variant_id=None,
                    variant_exists=None,
                    index_dir=index_dir,
                    debug_skips=debug_skips,
                    debug_skips_only_errors=debug_skips_only_errors,
                    reason="ambiguous_index_entry",
                )
                continue

            index_entry = index_entries[0]

            # 2. VALIDAR LA HIPÓTESIS VINCULADA
            if not index_entry.hypotheses:
                counters["skipped_no_hypothesis"] += 1
                _print_skip(
                    observation_ref,
                    "no_hypothesis",
                    f"No hypotheses listed in index {index_entry.index_path.name}.",
                    verbose,
                )
                _print_skip_debug(
                    observation_ref=observation_ref,
                    record=record,
                    index_entries=index_entries,
                    index_entry=index_entry,
                    hypothesis_path=None,
                    normalize_attempt=None,
                    extraction_attempt=None,
                    variant_parts=None,
                    variant_id=None,
                    variant_exists=None,
                    index_dir=index_dir,
                    debug_skips=debug_skips,
                    debug_skips_only_errors=debug_skips_only_errors,
                    reason="no_hypothesis",
                )
                continue

            if len(index_entry.hypotheses) > 1:
                counters["skipped_ambiguous_hypothesis"] += 1
                _print_skip(
                    observation_ref,
                    "ambiguous_hypothesis",
                    f"Multiple hypotheses listed in index {index_entry.index_path.name}.",
                    verbose,
                )
                _print_skip_debug(
                    observation_ref=observation_ref,
                    record=record,
                    index_entries=index_entries,
                    index_entry=index_entry,
                    hypothesis_path=None,
                    normalize_attempt=None,
                    extraction_attempt=None,
                    variant_parts=None,
                    variant_id=None,
                    variant_exists=None,
                    index_dir=index_dir,
                    debug_skips=debug_skips,
                    debug_skips_only_errors=debug_skips_only_errors,
                    reason="ambiguous_hypothesis",
                )
                continue

            # Construimos la ruta de la hipótesis relativa al root
            hypothesis_rel_path = index_entry.hypotheses[0]
            hypothesis_path = BRONZE_GPU_ROOT / hypothesis_rel_path

            if not hypothesis_path.exists():
                counters["skipped_missing_hypothesis"] += 1
                _print_skip(
                    observation_ref,
                    "missing_hypothesis_file",
                    f"Hypothesis file not found at {hypothesis_path}.",
                    verbose,
                )
                _print_skip_debug(
                    observation_ref=observation_ref,
                    record=record,
                    index_entries=index_entries,
                    index_entry=index_entry,
                    hypothesis_path=hypothesis_path,
                    normalize_attempt=None,
                    extraction_attempt=None,
                    variant_parts=None,
                    variant_id=None,
                    variant_exists=None,
                    index_dir=index_dir,
                    debug_skips=debug_skips,
                    debug_skips_only_errors=debug_skips_only_errors,
                    reason="missing_hypothesis_file",
                )
                continue

            # 3. PROCESAR HIPÓTESIS (LÓGICA IDÉNTICA A INGEST_VARIANTS)
            try:
                hypothesis_payload = json.loads(
                    hypothesis_path.read_text(encoding="utf-8")
                )
            except (OSError, json.JSONDecodeError) as exc:
                counters["errors"] += 1
                _print(
                    f"ERROR read hypothesis {hypothesis_path}: {exc}",
                    verbose,
                    force=True,
                )
                continue

            # === INICIO DE LÓGICA COMPARTIDA ===
            # Usamos exactamente las mismas funciones importadas
            extraction = hypothesis_payload.get("extraction") or {}

            normalize_attempt = try_match_with_normalize(
                hypothesis_payload, chip_index, vram_map
            )
            extraction_attempt = try_match_with_extraction(
                hypothesis_payload, chip_index, vram_map
            )

            # Prioridad idéntica al script original
            if normalize_attempt.chip_id:
                match_attempt = normalize_attempt
            else:
                match_attempt = extraction_attempt

            chip_id = match_attempt.chip_id
            vendor_id = match_attempt.vendor_id
            model_key = match_attempt.model_key
            vram_gb = match_attempt.vram_gb

            # AIB Manufacturer fallback logic idéntica
            aib_manufacturer = (
                normalize_attempt.aib_manufacturer
                if normalize_attempt.aib_manufacturer
                else extraction_attempt.aib_manufacturer
            )

            if not aib_manufacturer:
                counters["skipped_missing_fields"] += 1
                _print_skip(
                    observation_ref,
                    "missing_fields",
                    "Hypothesis missing AIB manufacturer.",
                    verbose,
                )
                variant_parts = _build_variant_parts_for_debug(
                    vendor_id,
                    model_key,
                    vram_gb,
                    aib_manufacturer,
                    extraction,
                )
                variant_id = _stable_variant_id(
                    [
                        variant_parts.get("vendor_id"),
                        variant_parts.get("model_key"),
                        variant_parts.get("vram_gb"),
                        variant_parts.get("aib_manufacturer"),
                        variant_parts.get("model_suffix"),
                        variant_parts.get("part_number"),
                    ]
                )
                cursor.execute(
                    "SELECT 1 FROM gpu_variant WHERE variant_id = ?",
                    (variant_id,),
                )
                variant_exists = cursor.fetchone() is not None
                _print_skip_debug(
                    observation_ref=observation_ref,
                    record=record,
                    index_entries=index_entries,
                    index_entry=index_entry,
                    hypothesis_path=hypothesis_path,
                    normalize_attempt=normalize_attempt,
                    extraction_attempt=extraction_attempt,
                    variant_parts=variant_parts,
                    variant_id=variant_id,
                    variant_exists=variant_exists,
                    index_dir=index_dir,
                    debug_skips=debug_skips,
                    debug_skips_only_errors=debug_skips_only_errors,
                    reason="missing_fields",
                )
                continue

            if chip_id is None:
                # Mapeo de errores idéntico
                if match_attempt.match_state == "missing":
                    counters["skipped_missing_fields"] += 1
                    reason = "missing_fields"
                    detail = "Required fields for matching are missing in hypothesis."
                elif match_attempt.match_state == "ambiguous":
                    counters["skipped_ambiguous_chip"] += 1
                    reason = "ambiguous_chip_match"
                    detail = "Multiple chips match criteria."
                else:
                    counters["skipped_no_chip_match"] += 1
                    reason = "no_chip_match"
                    detail = "No chip matches criteria."
                _print_skip(observation_ref, reason, detail, verbose)
                variant_parts = _build_variant_parts_for_debug(
                    vendor_id,
                    model_key,
                    vram_gb,
                    aib_manufacturer,
                    extraction,
                )
                variant_id = _stable_variant_id(
                    [
                        variant_parts.get("vendor_id"),
                        variant_parts.get("model_key"),
                        variant_parts.get("vram_gb"),
                        variant_parts.get("aib_manufacturer"),
                        variant_parts.get("model_suffix"),
                        variant_parts.get("part_number"),
                    ]
                )
                cursor.execute(
                    "SELECT 1 FROM gpu_variant WHERE variant_id = ?",
                    (variant_id,),
                )
                variant_exists = cursor.fetchone() is not None
                _print_skip_debug(
                    observation_ref=observation_ref,
                    record=record,
                    index_entries=index_entries,
                    index_entry=index_entry,
                    hypothesis_path=hypothesis_path,
                    normalize_attempt=normalize_attempt,
                    extraction_attempt=extraction_attempt,
                    variant_parts=variant_parts,
                    variant_id=variant_id,
                    variant_exists=variant_exists,
                    index_dir=index_dir,
                    debug_skips=debug_skips,
                    debug_skips_only_errors=debug_skips_only_errors,
                    reason=reason,
                )
                continue

            # Cálculo de Variant ID Determinista
            model_suffix = _coerce_str(
                extraction.get("aib_model_suffix") or extraction.get("model_suffix")
            )
            part_number = _coerce_str(extraction.get("part_number"))

            # Hash SHA256 con los mismos componentes
            variant_id = _stable_variant_id(
                [
                    vendor_id,
                    model_key,
                    vram_gb,
                    aib_manufacturer,
                    model_suffix,
                    part_number,
                ]
            )
            # === FIN DE LÓGICA COMPARTIDA ===

            # 4. EXTRACCIÓN DE DATOS DE MERCADO
            retailer = _coerce_str(record.get("retailer"))
            product_url = _coerce_str(record.get("product_url"))
            price_eur = _coerce_float(record.get("price_eur"))
            currency = _coerce_str(record.get("currency"))
            observed_at = _coerce_str(record.get("observed_at_utc"))
            scrape_run_id = _coerce_str(record.get("scrape_run_id"))
            sku = _coerce_str(record.get("sku"))
            stock_status = _coerce_str(record.get("stock_status"))

            if not retailer or not product_url or not observed_at or not scrape_run_id:
                counters["skipped_missing_fields"] += 1
                _print_skip(
                    observation_ref,
                    "missing_fields",
                    "Marketplace obs missing identifiers.",
                    verbose,
                )
                variant_parts = _build_variant_parts_for_debug(
                    vendor_id,
                    model_key,
                    vram_gb,
                    aib_manufacturer,
                    extraction,
                )
                cursor.execute(
                    "SELECT 1 FROM gpu_variant WHERE variant_id = ?",
                    (variant_id,),
                )
                variant_exists = cursor.fetchone() is not None
                _print_skip_debug(
                    observation_ref=observation_ref,
                    record=record,
                    index_entries=index_entries,
                    index_entry=index_entry,
                    hypothesis_path=hypothesis_path,
                    normalize_attempt=normalize_attempt,
                    extraction_attempt=extraction_attempt,
                    variant_parts=variant_parts,
                    variant_id=variant_id,
                    variant_exists=variant_exists,
                    index_dir=index_dir,
                    debug_skips=debug_skips,
                    debug_skips_only_errors=debug_skips_only_errors,
                    reason="missing_fields",
                )
                continue

            if currency is None and include_currency:
                counters["skipped_missing_fields"] += 1
                _print_skip(
                    observation_ref,
                    "missing_fields",
                    "Marketplace obs missing currency.",
                    verbose,
                )
                variant_parts = _build_variant_parts_for_debug(
                    vendor_id,
                    model_key,
                    vram_gb,
                    aib_manufacturer,
                    extraction,
                )
                cursor.execute(
                    "SELECT 1 FROM gpu_variant WHERE variant_id = ?",
                    (variant_id,),
                )
                variant_exists = cursor.fetchone() is not None
                _print_skip_debug(
                    observation_ref=observation_ref,
                    record=record,
                    index_entries=index_entries,
                    index_entry=index_entry,
                    hypothesis_path=hypothesis_path,
                    normalize_attempt=normalize_attempt,
                    extraction_attempt=extraction_attempt,
                    variant_parts=variant_parts,
                    variant_id=variant_id,
                    variant_exists=variant_exists,
                    index_dir=index_dir,
                    debug_skips=debug_skips,
                    debug_skips_only_errors=debug_skips_only_errors,
                    reason="missing_fields",
                )
                continue

            if price_eur is None or price_eur <= 0:
                counters["skipped_invalid_price"] += 1
                _print_skip(
                    observation_ref,
                    "invalid_price",
                    "Price is missing or invalid.",
                    verbose,
                )
                variant_parts = _build_variant_parts_for_debug(
                    vendor_id,
                    model_key,
                    vram_gb,
                    aib_manufacturer,
                    extraction,
                )
                cursor.execute(
                    "SELECT 1 FROM gpu_variant WHERE variant_id = ?",
                    (variant_id,),
                )
                variant_exists = cursor.fetchone() is not None
                _print_skip_debug(
                    observation_ref=observation_ref,
                    record=record,
                    index_entries=index_entries,
                    index_entry=index_entry,
                    hypothesis_path=hypothesis_path,
                    normalize_attempt=normalize_attempt,
                    extraction_attempt=extraction_attempt,
                    variant_parts=variant_parts,
                    variant_id=variant_id,
                    variant_exists=variant_exists,
                    index_dir=index_dir,
                    debug_skips=debug_skips,
                    debug_skips_only_errors=debug_skips_only_errors,
                    reason="invalid_price",
                )
                continue

            if stock_status is not None and stock_status not in ALLOWED_STOCK_STATUS:
                counters["skipped_invalid_stock_status"] += 1
                _print_skip(
                    observation_ref,
                    "invalid_stock_status",
                    f"Invalid status: {stock_status}",
                    verbose,
                )
                variant_parts = _build_variant_parts_for_debug(
                    vendor_id,
                    model_key,
                    vram_gb,
                    aib_manufacturer,
                    extraction,
                )
                cursor.execute(
                    "SELECT 1 FROM gpu_variant WHERE variant_id = ?",
                    (variant_id,),
                )
                variant_exists = cursor.fetchone() is not None
                _print_skip_debug(
                    observation_ref=observation_ref,
                    record=record,
                    index_entries=index_entries,
                    index_entry=index_entry,
                    hypothesis_path=hypothesis_path,
                    normalize_attempt=normalize_attempt,
                    extraction_attempt=extraction_attempt,
                    variant_parts=variant_parts,
                    variant_id=variant_id,
                    variant_exists=variant_exists,
                    index_dir=index_dir,
                    debug_skips=debug_skips,
                    debug_skips_only_errors=debug_skips_only_errors,
                    reason="invalid_stock_status",
                )
                continue

            # Generar ID único de la observación
            observation_id = _stable_observation_id(
                [variant_id, retailer, product_url, observed_at]
            )

            # 5. INSERCIÓN EN BASE DE DATOS
            if dry_run:
                cursor.execute(
                    "SELECT 1 FROM gpu_market_observation WHERE observation_id = ?",
                    (observation_id,),
                )
                if cursor.fetchone():
                    counters["skipped_duplicate"] += 1
                else:
                    counters["observations_inserted"] += 1
                    if verbose:
                        print(
                            f"DRY RUN insert {observation_ref} variant_id={variant_id} price={price_eur}"
                        )
                continue

            columns = [
                "observation_id",
                "variant_id",
                "retailer",
                "sku",
                "product_url",
                "price_eur",
                "stock_status",
                "observed_at",
                "scrape_run_id",
            ]
            values = [
                observation_id,
                variant_id,
                retailer,
                sku,
                product_url,
                price_eur,
                stock_status,
                observed_at,
                scrape_run_id,
            ]
            if include_currency:
                columns.append("currency")
                values.append(currency)

            try:
                cursor.execute(
                    f"""
                    INSERT INTO gpu_market_observation ({", ".join(columns)})
                    VALUES ({", ".join(["?"] * len(columns))})
                    ON CONFLICT(observation_id) DO NOTHING
                    """,
                    tuple(values),
                )
            except sqlite3.Error as exc:
                counters["errors"] += 1
                _print(f"ERROR insert {observation_ref}: {exc}", verbose, force=True)
                continue

            if cursor.rowcount == 0:
                counters["skipped_duplicate"] += 1
            else:
                counters["observations_inserted"] += 1
                if verbose:
                    print(
                        f"INSERT {observation_ref} variant_id={variant_id} price={price_eur}"
                    )

    if not dry_run:
        conn.commit()
    cursor.close()
    conn.close()

    print("\nSummary")
    for key in counters:
        if counters[key] > 0 or key == "errors":
            print(f"{key}: {counters[key]}")

    return 0 if counters["errors"] == 0 else 1


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest GPU marketplace observations into silver gpu_market_observation table."
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        help="SQLite database path",
    )
    parser.add_argument(
        "--marketplace-dir",
        type=Path,
        default=DEFAULT_MARKETPLACE_DIR,
        help="Directory containing marketplace observation JSON files",
    )
    parser.add_argument(
        "--index-dir",
        type=Path,
        default=DEFAULT_INDEX_DIR,
        help="Directory containing observed_product index JSON files",
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
        help="Process only the first N marketplace observations",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    parser.add_argument(
        "--debug-skips",
        action="store_true",
        help="Print detailed debug context for all skips",
    )
    parser.add_argument(
        "--debug-skips-only-errors",
        action="store_true",
        help="Print detailed debug context only for non-duplicate skips",
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    if not args.marketplace_dir.exists():
        print(f"Marketplace directory not found: {args.marketplace_dir}")
        return 1
    # Check index dir pero no salir si no existe, solo avisar (la funcion load_index_map maneja el vacio)
    if not args.index_dir.exists():
        print(f"WARNING: Index directory not found at {args.index_dir}")

    return ingest_market_observations(
        db_path=args.db_path,
        marketplace_dir=args.marketplace_dir,
        index_dir=args.index_dir,
        dry_run=args.dry_run,
        limit=args.limit,
        verbose=args.verbose,
        debug_skips=args.debug_skips,
        debug_skips_only_errors=args.debug_skips_only_errors,
    )


if __name__ == "__main__":
    raise SystemExit(main())
