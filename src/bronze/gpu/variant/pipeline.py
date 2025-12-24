from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any, Iterable

from .perplexity import extract_variant_hypothesis

BRONZE_GPU_ROOT = Path("data/bronze/gpu")
MARKETPLACE_ROOT = BRONZE_GPU_ROOT / "marketplace"
INDEX_ROOT = BRONZE_GPU_ROOT / "indexes" / "observed_product"
HYPOTHESES_ROOT = BRONZE_GPU_ROOT / "hypotheses" / "perplexity_ai"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("bronze.gpu.variant.pipeline")


def _generate_slug_name(extraction: dict[str, Any]) -> str:
    """
    Genera el slug: aib_model_chipset_vram_oc
    Ejemplo: asus_prime_nvidia_rtx5070ti_16gb_oc
    """
    parts = []

    # 1. AIB Manufacturer
    if val := extraction.get("aib_manufacturer"):
        parts.append(val.lower())

    # 2. AIB Model Suffix
    if val := extraction.get("aib_model_suffix"):
        parts.append(val.lower())

    # 3. Chipset Manufacturer
    if val := extraction.get("chipset_manufacturer"):
        parts.append(val.lower())

    # 4. Chipset Model (limpieza de espacios y marcas comerciales)
    if val := extraction.get("chipset_model"):
        # Removemos "geforce", "rtx", "radeon" etc si se repiten o queremos un slug limpio
        clean_model = (
            val.lower().replace("geforce", "").replace("rtx", "rtx").replace(" ", "")
        )
        parts.append(clean_model)

    # 5. VRAM (Opcional)
    vram = extraction.get("vram_gb")
    if vram is not None:
        parts.append(f"{vram}gb")

    # 6. OC (Opcional)
    if extraction.get("is_oc") is True:
        parts.append("oc")

    # Unir todo con guiones bajos y limpiar caracteres no deseados
    slug = "_".join(parts)
    return re.sub(r"[^a-z0-9_]", "", slug)


def _hash_url(url: str) -> str:
    """Genera el ID único basado en la URL del producto"""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def _iter_marketplace_files() -> Iterable[Path]:
    return sorted(MARKETPLACE_ROOT.glob("**/runs/**/page_pg=*.products.json"))


def _load_marketplace_file(path: Path) -> list[dict[str, Any]]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return [item for item in data if isinstance(item, dict)]
    except Exception as exc:
        logger.error("Failed to read/parse %s: %s", path, exc)
        return []


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=True, indent=2)


def run_pipeline() -> None:
    marketplace_files = list(_iter_marketplace_files())
    logger.info("Found %d marketplace files", len(marketplace_files))

    stats = {"processed": 0, "created": 0, "skipped": 0, "errors": 0}

    for marketplace_file in marketplace_files:
        records = _load_marketplace_file(marketplace_file)
        relative_marketplace = marketplace_file.relative_to(BRONZE_GPU_ROOT).as_posix()

        for index, record in enumerate(records):
            stats["processed"] += 1

            product_url = record.get("product_url")
            product_name_raw = record.get("product_name_raw")

            if not product_url or not product_name_raw:
                logger.warning(
                    "Missing URL or Name in %s#%d", relative_marketplace, index
                )
                stats["errors"] += 1
                continue

            # El ID se basa en la URL para evitar re-procesar el mismo link
            observed_product_id = _hash_url(product_url)
            index_path = INDEX_ROOT / f"{observed_product_id}.json"

            # Skip si ya tenemos esta URL indexada
            if index_path.exists():
                stats["skipped"] += 1
                continue

            try:
                # 1. Llamada a Perplexity
                variant_hypothesis = extract_variant_hypothesis(product_name_raw)

                # 2. Extraer datos para el slug
                extraction_data = variant_hypothesis.get("extraction", {})
                normalized_name = _generate_slug_name(extraction_data)

                # 3. Guardar Hipótesis
                hypothesis_relative = (
                    Path("hypotheses/perplexity_ai") / f"{observed_product_id}.json"
                )
                _write_json(BRONZE_GPU_ROOT / hypothesis_relative, variant_hypothesis)

                # 4. Crear registro de índice
                index_record = {
                    "observed_product_id": observed_product_id,
                    "normalized_name": normalized_name,
                    "product_url": product_url,
                    "first_seen_at": record.get("observed_at_utc"),
                    "retailer": record.get("retailer"),
                    "marketplace_observations": [f"{relative_marketplace}#{index}"],
                    "hypotheses": [hypothesis_relative.as_posix()],
                }
                _write_json(index_path, index_record)

                stats["created"] += 1
                logger.info(
                    "Enriched: %s -> %s", product_name_raw[:30], normalized_name
                )

            except Exception as exc:
                logger.error(
                    "Pipeline error for %s: %s", product_url, exc, exc_info=True
                )
                stats["errors"] += 1

    logger.info("Pipeline complete: %s", stats)


if __name__ == "__main__":
    run_pipeline()
