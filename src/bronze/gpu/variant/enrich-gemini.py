# POC
import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from typing import Optional, List, Any

from pydantic import BaseModel

# --- Importaciones ---
try:
    from google import genai
    from google.genai import types
    from google.api_core import exceptions
except ImportError:
    print("Error: Falta librería. Ejecuta: pip install google-genai")
    sys.exit(1)

# --- Configuración de Logs ---
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger("GPU_Enricher")

MODEL_NAME = (
    "gemini-2.5-flash-lite"  # Actualizado a la versión lite más reciente de 2025
)

# --- 1. Modelos de Datos (Estructura Estricta) ---


class ExtractionSpecs(BaseModel):
    aib_manufacturer: Optional[str] = None
    aib_model_suffix: Optional[str] = None
    chipset_manufacturer: Optional[str] = None
    chipset_model: Optional[str] = None
    vram_gb: Optional[int] = None
    is_oc: bool = False
    factory_boost_mhz: Optional[int] = None
    part_number: Optional[str] = None
    length_mm: Optional[int] = None
    width_slots: Optional[float] = None
    height_mm: Optional[int] = None
    power_connectors: Optional[str] = None
    cooling_type: Optional[str] = "Air"
    fan_count: Optional[int] = None
    displayport_count: Optional[int] = 0
    displayport_version: Optional[str] = None
    hdmi_count: Optional[int] = 0
    hdmi_version: Optional[str] = None
    warranty_years: Optional[int] = None


class FinalOutput(BaseModel):
    hypothesis_type: str = "gpu_variant"
    source: str = "gemini_model"
    created_at: str
    input: dict
    extraction: ExtractionSpecs
    evidence: dict
    raw: dict


# --- 2. Lógica del Agente ---


def enrich_gpu_data(model_input: str, max_retries: int = 3) -> Optional[dict]:
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        logger.error("La variable de entorno GOOGLE_API_KEY no está configurada.")
        return None

    client = genai.Client(api_key=api_key)

    # Configuración de búsqueda de Google
    google_search_tool = types.Tool(google_search=types.GoogleSearch())

    prompt = f"""
    Extrae los datos técnicos detallados de la siguiente GPU: {model_input}
    
    REGLAS:
    1. Identifica el 'part_number' (MPN) si está presente.
    2. Determina 'aib_manufacturer' (ej. ASUS, MSI) y 'chipset_manufacturer' (NVIDIA, AMD).
    3. 'width_slots' debe ser un número (ej. 2.5).
    4. Si un valor no se encuentra, usa null.
    5. Devuelve la información estrictamente en formato JSON que coincida con la estructura de 'extraction'.
    """

    # Log de inicio según formato solicitado
    print(f"[INFO] Step 1: Searching for official URL for {model_input.strip()}")

    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction="Eres un experto en hardware. Tu salida debe ser exclusivamente JSON.",
                    tools=[google_search_tool],
                    temperature=0.0,
                ),
            )

            # Extraer URL de evidencia de los metadatos de Google Search
            source_url = None
            if (
                response.candidates[0].grounding_metadata
                and response.candidates[0].grounding_metadata.search_entry_point
            ):
                # Intentamos obtener el primer link relevante de los chunks de búsqueda
                sources = response.candidates[0].grounding_metadata.grounding_chunks
                if sources:
                    for chunk in sources:
                        if chunk.web and chunk.web.uri:
                            source_url = chunk.web.uri
                            break

            print(f"[INFO] Found URL: {source_url or 'Not found'}")
            print(f"[INFO] Step 2: Extracting specs via Gemini...")

            # Construcción del objeto final
            extraction_data = response.parsed if response.parsed else ExtractionSpecs()

            final_obj = FinalOutput(
                created_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                input={"model_name": model_input},
                extraction=extraction_data,
                evidence={
                    "source_url": source_url,
                    "citations": [],  # Gemini 2.0 API maneja citas en grounding_metadata si es necesario
                },
                raw={
                    "llm_response": f"```json\n{json.dumps(extraction_data.model_dump(), indent=2)}\n```"
                },
            )

            return final_obj.model_dump()

        except exceptions.ResourceExhausted:
            wait = (attempt + 1) * 30
            logger.warning(f"Cuota excedida. Reintentando en {wait}s...")
            time.sleep(wait)
        except Exception as e:
            logger.error(f"Error crítico: {e}")
            break

    return None


# --- Entry Point ---

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GPU Spec Extractor Gemini 2025")
    parser.add_argument("model_name", help="Nombre o MPN de la GPU")
    args = parser.parse_args()

    result = enrich_gpu_data(args.model_name)

    if result:
        # Imprimir el resultado final en JSON puro
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        sys.exit(1)
