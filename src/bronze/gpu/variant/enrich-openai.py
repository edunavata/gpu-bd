#!/usr/bin/env python3
import argparse
import json
import logging
import os
import sys
import re
from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field

# --- Importaciones ---
try:
    from openai import OpenAI
    from tavily import TavilyClient
except ImportError as e:
    print(f"Error crítico: Falta librería. {e}")
    print("Ejecuta: pip install openai pydantic tavily-python")
    sys.exit(1)

# --- Configuración ---
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger("GPU_Agent")

MODEL_NAME = "gpt-4o-2024-08-06"  # Soporta Structured Outputs nativos


# --- 1. Modelos de Datos (Estructura JSON Estricta) ---
class TechnicalSpecs(BaseModel):
    aib_manufacturer: str = Field(..., description="Ej: ASUS, Gigabyte, MSI")
    model_suffix: Optional[str] = Field(
        None, description="Ej: Dual, Gaming OC, ROG Strix"
    )
    factory_boost_mhz: Optional[int] = None
    length_mm: Optional[int] = None
    width_slots: Optional[float] = None
    height_mm: Optional[float] = None
    power_connectors: Optional[str] = Field(None, description="Ej: 1x 16-pin")
    cooling_type: str = Field(..., description="Air, Liquid, or Hybrid")
    fan_count: Optional[int] = None
    displayport_count: int = 0
    displayport_version: Optional[str] = None
    hdmi_count: int = 0
    hdmi_version: Optional[str] = None
    warranty_years: Optional[int] = None


class GPUFullResponse(BaseModel):
    aib_manufacturer: str
    chipset: str = Field(
        ..., description="Nombre del chipset completo, ej: NVIDIA GeForce RTX 5070"
    )
    model_suffix: Optional[str]
    is_oc: bool
    vram_gb: Optional[int]
    extraction: TechnicalSpecs


# --- 2. Utilidades ---
def sanitize_input(raw_input: str) -> str:
    clean = raw_input.strip()
    clean = re.split(r"[\r\n]", clean)[0]
    return clean


# --- 3. Motor de Búsqueda (Tavily) ---
def get_search_context(query: str) -> str:
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        return "Search unavailable (No API Key)."

    tavily = TavilyClient(api_key=api_key)
    logger.info(f"Buscando ficha técnica para: '{query}'")

    try:
        # Buscamos específicamente la hoja de especificaciones
        response = tavily.search(
            query=f"{query} official tech specs dimensions power",
            search_depth="advanced",
            max_results=5,
        )

        context_parts = [
            f"Source: {r['url']}\nContent: {r['content']}"
            for r in response.get("results", [])
        ]
        return "\n\n".join(context_parts)
    except Exception as e:
        logger.error(f"Error en búsqueda: {e}")
        return ""


# --- 4. Cerebro (OpenAI) ---
def extract_specs(raw_model_name: str) -> dict:
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    clean_name = sanitize_input(raw_model_name)
    context = get_search_context(clean_name)

    system_prompt = """
    Eres un experto en hardware. Tu tarea es extraer información de una GPU.
    
    INSTRUCCIONES DE EXTRACCIÓN:
    1. Del 'INPUT' del usuario, extrae:
       - aib_manufacturer: La marca (ASUS, MSI, etc).
       - chipset: El modelo base (NVIDIA GeForce RTX..., AMD Radeon...).
       - model_suffix: La sub-marca (Dual, TUF, Trinity).
       - is_oc: true si el nombre contiene 'OC'.
       - vram_gb: el número de GB de VRAM.
       
    2. Del 'SEARCH CONTEXT', extrae los detalles técnicos para el objeto 'extraction'.
    3. Si un dato técnico no existe en el contexto, déjalo como null.
    4. Sé estricto con los tipos de datos (longitud en mm como entero, slots como float).
    """

    user_message = f"""
    INPUT: "{clean_name}"
    
    === SEARCH CONTEXT ===
    {context}
    ======================
    """

    try:
        completion = client.beta.chat.completions.parse(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            response_format=GPUFullResponse,
        )

        return completion.choices[0].message.parsed.model_dump(mode="json")

    except Exception as e:
        logger.error(f"Fallo en la extracción: {e}")
        return {"status": "error", "message": str(e)}


# --- Entry Point (CLI) ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Extractor de especificaciones de GPU vía API"
    )
    parser.add_argument(
        "model_name",
        help="Nombre completo de la GPU (ej: 'ASUS Dual GeForce RTX 5070 OC')",
    )
    args = parser.parse_args()

    if not os.getenv("OPENAI_API_KEY") or not os.getenv("TAVILY_API_KEY"):
        print(
            "Error: Debes configurar OPENAI_API_KEY y TAVILY_API_KEY en tus variables de entorno."
        )
        sys.exit(1)

    result = extract_specs(args.model_name)
    print(json.dumps(result, indent=2, ensure_ascii=False))
