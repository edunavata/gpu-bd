#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import requests

# --- Configuración de Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

# --- Configuración de Perplexity ---
CHAT_API_URL = "https://api.perplexity.ai/chat/completions"
SEARCH_API_URL = "https://api.perplexity.ai/search"
CHAT_MODEL = "sonar"  # O "sonar-pro" según disponibilidad

# --- Prompts ---
SYSTEM_PROMPT = """
You are a strict hardware specification extraction agent.

ABSOLUTE PRIORITY RULE:
You are provided with a specific URL context.
You MUST extract data ONLY from that source.
If the data is not explicitly present in the provided content, return null.

CRITICAL NORMALIZATION RULES (MANDATORY):
- All proper nouns MUST be returned in their CANONICAL OFFICIAL FORM.
- NEVER humanize, re-case, or simplify brand or product names.
- Preserve exact vendor capitalization:
  - "NVIDIA", "AMD", "GeForce", "RTX", "Radeon", "RX"
- Example:
  ❌ "Geforce Rtx 5060 Ti"
  ✅ "GeForce RTX 5060 Ti"

Field-specific normalization:
- aib_manufacturer: Official brand name only (e.g. "ASUS", "MSI", "Gigabyte").
- model_suffix / aib_model_suffix:
  - Short, normalized AIB family name ONLY.
  - Examples: "Prime", "ROG Strix", "TUF Gaming", "Gaming OC".
  - NEVER include chipset names, VRAM size, or OC descriptors unless they are part of the official suffix.
- chipset_model:
  - MUST be the canonical NVIDIA / AMD product name.
  - Examples:
    - "GeForce RTX 5060 Ti"
    - "Radeon RX 7800 XT"

STRICT NULL POLICY:
- If a value is not explicitly stated in the source, return null.
- DO NOT infer, guess, or normalize from memory.

Output MUST be valid JSON ONLY.
NO markdown.
NO comments.
NO explanations.
"""

USER_PROMPT_TEMPLATE = """
I have identified this URL as the likely official source:
{source_url}

Please analyze the content of that page/product and return the JSON for the GPU:
"{model_name}"

STRICT REQUIREMENTS:
- All names MUST be returned in their OFFICIAL CANONICAL FORM.
- Preserve exact capitalization (e.g. "GeForce RTX 5060 Ti", NOT "Geforce Rtx 5060 Ti").
- aib_model_suffix must be a SHORT normalized family name (e.g. "Prime", "Gaming OC").
- If a value is not explicitly present, return null.

Strict rule:
"part_number" must be null unless explicitly labeled as Part Number, MPN, or Product Number in the provided source.

Schema:
{{
"aib_manufacturer": string,
"model_suffix": string | null,
"factory_boost_mhz": integer | null,
"part_number": string | null,
"length_mm": integer | null,
"width_slots": number | null,
"height_mm": integer | null,
"power_connectors": string | null,
"cooling_type": "Air" | "Liquid" | "Hybrid" | null,
"fan_count": integer | null,
"displayport_count": integer | null,
"displayport_version": string | null,
"hdmi_count": integer | null,
"hdmi_version": string | null,
"warranty_years": integer | null
}}
"""

EXTRACTION_FIELDS = [
    "aib_manufacturer",
    "model_suffix",
    "factory_boost_mhz",
    "part_number",
    "length_mm",
    "width_slots",
    "height_mm",
    "power_connectors",
    "cooling_type",
    "fan_count",
    "displayport_count",
    "displayport_version",
    "hdmi_count",
    "hdmi_version",
    "warranty_years",
]


# --- Utilidades ---
def _get_api_key() -> str:
    api_key = os.getenv("PERPLEXITY_API_KEY")
    if not api_key:
        logger.error("Environment variable PERPLEXITY_API_KEY is missing.")
        raise RuntimeError("Missing PERPLEXITY_API_KEY")
    return api_key


def _clean_and_parse_json(raw_text: str) -> Dict[str, Any]:
    """Extrae y parsea JSON del output del LLM con robustez."""
    raw_text = raw_text.strip()
    # Intento 1: Parseo directo
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        pass

    # Intento 2: Buscar bloques de código Markdown
    code_block_pattern = r"```(?:json)?\s*(\{.*?\})\s*```"
    match = re.search(code_block_pattern, raw_text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Intento 3: Buscar por llaves {}
    try:
        start = raw_text.index("{")
        end = raw_text.rindex("}") + 1
        return json.loads(raw_text[start:end])
    except (ValueError, json.JSONDecodeError):
        logger.error(f"Failed to parse JSON from: {raw_text[:100]}...")
        raise ValueError("No valid JSON object found in LLM output")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _derive_chipset_fields(model_name: str) -> Dict[str, Any]:
    """
    Derive chipset-related fields deterministically from the raw model name.
    No LLM involvement.
    """
    text = model_name.upper()

    chipset_manufacturer = None
    if "RTX" in text or "GEFORCE" in text:
        chipset_manufacturer = "NVIDIA"
    elif "RADEON" in text or "RX" in text:
        chipset_manufacturer = "AMD"

    chipset_model = None
    match = re.search(
        r"(GEFORCE RTX \d{4}\s?TI?|GEFORCE RTX \d{4}|RADEON RX \d{4}\s?XT?)",
        text,
    )
    if match:
        chipset_model = match.group(1).title()

    vram_gb = None
    vram_match = re.search(r"(\d{2})\s*GB", text)
    if vram_match:
        vram_gb = int(vram_match.group(1))

    is_oc = any(token in text for token in [" OC", "-OC", " O.C", " OVERCLOCK"])

    return {
        "chipset_manufacturer": chipset_manufacturer,
        "chipset_model": chipset_model,
        "vram_gb": vram_gb,
        "is_oc": is_oc,
    }


def _derive_aib_model_suffix(
    extracted: Dict[str, Any], model_name: str
) -> Optional[str]:
    """
    Extract a clean AIB model suffix (e.g. 'Prime', 'Strix', 'Gaming X').
    Prefers LLM output, falls back to heuristic.
    """
    raw_suffix = extracted.get("model_suffix")
    if raw_suffix:
        # Strip chipset noise if LLM returned a long string
        raw_suffix = re.sub(r"GEFORCE RTX.*", "", raw_suffix, flags=re.I).strip()
        return raw_suffix or None

    # Fallback heuristic
    match = re.search(
        r"(PRIME|STRIX|TUF|GAMING|VENTUS|SUPRIM|PULSE|NITRO\+?)",
        model_name.upper(),
    )
    return match.group(1).title() if match else None


# --- Lógica de API ---
def _find_official_url(model_name: str) -> Optional[str]:
    """Busca la URL oficial usando el endpoint de búsqueda."""
    headers = {
        "Authorization": f"Bearer {_get_api_key()}",
        "Content-Type": "application/json",
    }
    payload = {"query": f"{model_name} official specifications page", "max_results": 3}

    try:
        logger.info(f"Step 1: Searching for official URL for {model_name}...")
        resp = requests.post(SEARCH_API_URL, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()

        results = resp.json().get("results", [])
        if not results:
            return None

        top_url = results[0].get("url")
        logger.info(f"Found URL: {top_url}")
        return top_url
    except Exception as e:
        logger.error(f"Search API failed: {e}")
        return None


def _call_chat_api(model_name: str, source_url: Optional[str]) -> tuple[str, list]:
    """Extrae datos técnicos mediante el modelo de chat."""
    headers = {
        "Authorization": f"Bearer {_get_api_key()}",
        "Content-Type": "application/json",
    }

    url_context = (
        source_url if source_url else "Perform a broad search for official specs."
    )

    payload = {
        "model": CHAT_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT.strip()},
            {
                "role": "user",
                "content": USER_PROMPT_TEMPLATE.format(
                    model_name=model_name, source_url=url_context
                ).strip(),
            },
        ],
        "temperature": 0.0,
    }

    try:
        logger.info("Step 2: Extracting specs via Sonar...")
        resp = requests.post(CHAT_API_URL, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()

        data = resp.json()
        message = data["choices"][0]["message"]
        return message["content"], message.get("citations", [])
    except Exception as e:
        logger.error(f"Chat API failed: {e}")
        raise


def extract_variant_hypothesis(model_name: str) -> Dict[str, Any]:
    """Orquesta la búsqueda y extracción para generar la hipótesis."""
    found_url = _find_official_url(model_name)
    content, citations = _call_chat_api(model_name, found_url)
    extracted = _clean_and_parse_json(content)

    chipset_fields = _derive_chipset_fields(model_name)
    aib_model_suffix = _derive_aib_model_suffix(extracted, model_name)

    clean_extraction = {
        "aib_manufacturer": extracted.get("aib_manufacturer"),
        "aib_model_suffix": aib_model_suffix,
        "chipset_manufacturer": chipset_fields["chipset_manufacturer"],
        "chipset_model": chipset_fields["chipset_model"],
        "vram_gb": chipset_fields["vram_gb"],
        "is_oc": chipset_fields["is_oc"],
        "factory_boost_mhz": extracted.get("factory_boost_mhz"),
        "part_number": extracted.get("part_number"),
        "length_mm": extracted.get("length_mm"),
        "width_slots": extracted.get("width_slots"),
        "height_mm": extracted.get("height_mm"),
        "power_connectors": extracted.get("power_connectors"),
        "cooling_type": extracted.get("cooling_type"),
        "fan_count": extracted.get("fan_count"),
        "displayport_count": extracted.get("displayport_count"),
        "displayport_version": extracted.get("displayport_version"),
        "hdmi_count": extracted.get("hdmi_count"),
        "hdmi_version": extracted.get("hdmi_version"),
        "warranty_years": extracted.get("warranty_years"),
    }

    return {
        "hypothesis_type": "gpu_variant",
        "source": "perplexity_ai",
        "created_at": _utc_now_iso(),
        "input": {"model_name": model_name},
        "extraction": clean_extraction,
        "evidence": {
            "source_url": found_url,
            "citations": citations or [],
        },
        "raw": {"llm_response": content},
    }


# --- Punto de Entrada ---
def main() -> None:
    parser = argparse.ArgumentParser(
        description="GPU Spec Extractor using Perplexity AI"
    )
    parser.add_argument(
        "model_name", help="Full GPU variant name (e.g., 'ASUS ROG Strix RTX 4080')"
    )
    args = parser.parse_args()

    try:
        result = extract_variant_hypothesis(args.model_name)
        print(json.dumps(result, indent=2))
    except Exception as e:
        logger.error(f"Process failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
