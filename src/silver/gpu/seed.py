from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Iterator

from src.common.db import get_connection


SEED_DIR = Path("seeds/silver/gpu/canonical")

CHIP_FIELDS = (
    "vendor",
    "brand_series",
    "model_name",
    "code_name",
    "architecture",
    "process_node_nm",
    "launch_date",
    "compute_units_type",
    "compute_units_count",
    "rt_cores",
    "tensor_cores",
    "base_clock_mhz",
    "boost_clock_mhz",
    "tdp_watts",
    "recommended_psu_watts",
    "pcie_generation",
    "pcie_lanes",
)

MEMORY_FIELDS = (
    "vram_gb",
    "memory_type",
    "memory_bus_bits",
    "memory_speed_gbps",
    "memory_bandwidth_gbs",
)

FEATURE_FIELDS = (
    "raytracing_hardware",
    "raytracing_api_support",
    "cuda_compute_capability",
    "dlss_version",
    "nvenc_generation",
    "nvidia_reflex",
    "fsr_support",
    "amd_fmf",
    "amd_hypr_rx",
    "xess_support",
    "av1_encode",
    "av1_decode",
    "resizable_bar",
)

CHIP_UPSERT_SQL = """
INSERT INTO gpu_chip (
    chip_id,
    vendor_id,
    brand_series,
    model_name,
    code_name,
    architecture_id,
    process_node_nm,
    launch_date,
    compute_units_type,
    compute_units_count,
    rt_cores,
    tensor_cores,
    base_clock_mhz,
    boost_clock_mhz,
    tdp_watts,
    recommended_psu_watts,
    pcie_generation,
    pcie_lanes
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(chip_id) DO UPDATE SET
    vendor_id = excluded.vendor_id,
    brand_series = excluded.brand_series,
    model_name = excluded.model_name,
    code_name = excluded.code_name,
    architecture_id = excluded.architecture_id,
    process_node_nm = excluded.process_node_nm,
    launch_date = excluded.launch_date,
    compute_units_type = excluded.compute_units_type,
    compute_units_count = excluded.compute_units_count,
    rt_cores = excluded.rt_cores,
    tensor_cores = excluded.tensor_cores,
    base_clock_mhz = excluded.base_clock_mhz,
    boost_clock_mhz = excluded.boost_clock_mhz,
    tdp_watts = excluded.tdp_watts,
    recommended_psu_watts = excluded.recommended_psu_watts,
    pcie_generation = excluded.pcie_generation,
    pcie_lanes = excluded.pcie_lanes,
    updated_at = CURRENT_TIMESTAMP
"""

MEMORY_UPSERT_SQL = """
INSERT INTO gpu_memory (
    chip_id,
    vram_gb,
    memory_type_id,
    memory_bus_bits,
    memory_speed_gbps,
    memory_bandwidth_gbs
)
VALUES (?, ?, ?, ?, ?, ?)
ON CONFLICT(chip_id) DO UPDATE SET
    vram_gb = excluded.vram_gb,
    memory_type_id = excluded.memory_type_id,
    memory_bus_bits = excluded.memory_bus_bits,
    memory_speed_gbps = excluded.memory_speed_gbps,
    memory_bandwidth_gbs = excluded.memory_bandwidth_gbs
"""

FEATURES_UPSERT_SQL = """
INSERT INTO gpu_features (
    chip_id,
    raytracing_hardware,
    raytracing_api_support,
    cuda_compute_capability,
    dlss_version,
    nvenc_generation,
    nvidia_reflex,
    fsr_support,
    amd_fmf,
    amd_hypr_rx,
    xess_support,
    av1_encode,
    av1_decode,
    resizable_bar
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(chip_id) DO UPDATE SET
    raytracing_hardware = excluded.raytracing_hardware,
    raytracing_api_support = excluded.raytracing_api_support,
    cuda_compute_capability = excluded.cuda_compute_capability,
    dlss_version = excluded.dlss_version,
    nvenc_generation = excluded.nvenc_generation,
    nvidia_reflex = excluded.nvidia_reflex,
    fsr_support = excluded.fsr_support,
    amd_fmf = excluded.amd_fmf,
    amd_hypr_rx = excluded.amd_hypr_rx,
    xess_support = excluded.xess_support,
    av1_encode = excluded.av1_encode,
    av1_decode = excluded.av1_decode,
    resizable_bar = excluded.resizable_bar
"""


def _stable_id(prefix: str, parts: Iterable[Any]) -> str:
    normalized_parts = []
    for part in parts:
        if part is None:
            normalized_parts.append("")
        elif isinstance(part, bool):
            normalized_parts.append("true" if part else "false")
        else:
            normalized_parts.append(str(part).strip().lower())
    digest = hashlib.sha256("|".join(normalized_parts).encode("utf-8")).hexdigest()
    return f"{prefix}_{digest}"


def _normalize_reference(value: Any) -> str:
    return "".join(ch for ch in str(value).strip().lower() if ch.isalnum())


def _load_reference_map(cursor, table: str, id_column: str) -> dict[str, str]:
    cursor.execute(f"SELECT {id_column} FROM {table}")
    mapping: dict[str, str] = {}
    for row in cursor.fetchall():
        ref_id = row[0]
        if ref_id is None:
            continue
        key = _normalize_reference(ref_id)
        if key in mapping and mapping[key] != ref_id:
            raise ValueError(
                f"Ambiguous {table} identifiers for key '{key}': "
                f"{mapping[key]} vs {ref_id}"
            )
        mapping[key] = ref_id
    return mapping


def _resolve_reference(
    value: Any,
    mapping: dict[str, str],
    table: str,
    field: str,
    source: Path,
    index: int,
) -> str:
    if value is None:
        raise ValueError(
            f"{source} entry {index} missing {field} value for {table} lookup"
        )
    key = _normalize_reference(value)
    ref_id = mapping.get(key)
    if ref_id is None:
        raise ValueError(
            f"{source} entry {index} has unknown {field} '{value}' for {table}"
        )
    return ref_id


def _load_seed_file(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise ValueError(f"{path} root must be a list")
    return data


def _iter_seed_entries(seed_dir: Path) -> Iterator[tuple[Path, int, dict[str, Any]]]:
    if not seed_dir.exists():
        raise FileNotFoundError(f"Seed directory not found: {seed_dir}")
    seed_files = sorted(seed_dir.glob("*.json"))
    if not seed_files:
        raise FileNotFoundError(f"No seed files found in {seed_dir}")
    for path in seed_files:
        data = _load_seed_file(path)
        for index, entry in enumerate(data):
            if not isinstance(entry, dict):
                raise ValueError(f"{path} entry {index} must be an object")
            yield path, index, entry


def _require_fields(obj: dict[str, Any], fields: Iterable[str], context: str) -> None:
    missing = [field for field in fields if field not in obj]
    if missing:
        raise ValueError(f"{context} missing required fields: {', '.join(missing)}")


def _parse_entry(
    entry: dict[str, Any],
    source: Path,
    index: int,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    if "chip" not in entry:
        raise ValueError(f"{source} entry {index} missing 'chip'")
    if "memory" not in entry:
        raise ValueError(f"{source} entry {index} missing 'memory'")
    if "features" not in entry:
        raise ValueError(f"{source} entry {index} missing 'features'")

    chip = entry["chip"]
    memory = entry["memory"]
    features = entry["features"]

    if not isinstance(chip, dict):
        raise ValueError(f"{source} entry {index} chip must be an object")
    if not isinstance(memory, dict):
        raise ValueError(f"{source} entry {index} memory must be an object")
    if not isinstance(features, dict):
        raise ValueError(f"{source} entry {index} features must be an object")

    _require_fields(chip, CHIP_FIELDS, f"{source} entry {index} chip")
    _require_fields(memory, MEMORY_FIELDS, f"{source} entry {index} memory")
    _require_fields(features, FEATURE_FIELDS, f"{source} entry {index} features")

    return chip, memory, features


def _entry_signature(
    chip: dict[str, Any],
    memory: dict[str, Any],
    features: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    return chip, memory, features


def _chip_id_parts(chip: dict[str, Any], memory: dict[str, Any]) -> list[Any]:
    return [chip[field] for field in CHIP_FIELDS] + [
        memory[field] for field in MEMORY_FIELDS
    ]


def _chip_id(chip: dict[str, Any], memory: dict[str, Any]) -> str:
    return _stable_id("chip", _chip_id_parts(chip, memory))


def _insert_chip(
    cursor,
    chip_id: str,
    chip: dict[str, Any],
    vendor_id: str,
    architecture_id: str,
) -> None:
    cursor.execute(
        CHIP_UPSERT_SQL,
        (
            chip_id,
            vendor_id,
            chip["brand_series"],
            chip["model_name"],
            chip["code_name"],
            architecture_id,
            chip["process_node_nm"],
            chip["launch_date"],
            chip["compute_units_type"],
            chip["compute_units_count"],
            chip["rt_cores"],
            chip["tensor_cores"],
            chip["base_clock_mhz"],
            chip["boost_clock_mhz"],
            chip["tdp_watts"],
            chip["recommended_psu_watts"],
            chip["pcie_generation"],
            chip["pcie_lanes"],
        ),
    )


def _insert_memory(
    cursor,
    chip_id: str,
    memory: dict[str, Any],
    memory_type_id: str,
) -> None:
    cursor.execute(
        MEMORY_UPSERT_SQL,
        (
            chip_id,
            memory["vram_gb"],
            memory_type_id,
            memory["memory_bus_bits"],
            memory["memory_speed_gbps"],
            memory["memory_bandwidth_gbs"],
        ),
    )


def _insert_features(cursor, chip_id: str, features: dict[str, Any]) -> None:
    cursor.execute(
        FEATURES_UPSERT_SQL,
        (
            chip_id,
            features["raytracing_hardware"],
            features["raytracing_api_support"],
            features["cuda_compute_capability"],
            features["dlss_version"],
            features["nvenc_generation"],
            features["nvidia_reflex"],
            features["fsr_support"],
            features["amd_fmf"],
            features["amd_hypr_rx"],
            features["xess_support"],
            features["av1_encode"],
            features["av1_decode"],
            features["resizable_bar"],
        ),
    )


def seed() -> dict[str, int]:
    conn = get_connection()
    cursor = conn.cursor()
    vendor_map = _load_reference_map(cursor, "gpu_vendor", "vendor_id")
    architecture_map = _load_reference_map(cursor, "gpu_architecture", "architecture_id")
    memory_type_map = _load_reference_map(cursor, "gpu_memory_type", "memory_type_id")
    seen: dict[str, tuple[dict[str, Any], dict[str, Any], dict[str, Any]]] = {}
    seeded = {"chips": 0}

    try:
        conn.execute("BEGIN")
        for source, index, entry in _iter_seed_entries(SEED_DIR):
            chip, memory, features = _parse_entry(entry, source, index)
            vendor_id = _resolve_reference(
                chip["vendor"],
                vendor_map,
                "gpu_vendor",
                "vendor",
                source,
                index,
            )
            architecture_id = _resolve_reference(
                chip["architecture"],
                architecture_map,
                "gpu_architecture",
                "architecture",
                source,
                index,
            )
            memory_type_id = _resolve_reference(
                memory["memory_type"],
                memory_type_map,
                "gpu_memory_type",
                "memory_type",
                source,
                index,
            )
            chip_id = _chip_id(chip, memory)
            signature = _entry_signature(chip, memory, features)

            if chip_id in seen:
                if seen[chip_id] != signature:
                    raise ValueError(
                        f"{source} entry {index} conflicts with existing chip_id {chip_id}"
                    )
                continue

            seen[chip_id] = signature
            _insert_chip(cursor, chip_id, chip, vendor_id, architecture_id)
            _insert_memory(cursor, chip_id, memory, memory_type_id)
            _insert_features(cursor, chip_id, features)

            seeded["chips"] += 1

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()

    return seeded


def main() -> None:
    result = seed()
    print(f"Seeded {result['chips']} chips from {SEED_DIR}")


if __name__ == "__main__":
    main()
