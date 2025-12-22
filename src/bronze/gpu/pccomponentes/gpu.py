from __future__ import annotations
import json
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright

# Opcional pero recomendado: from playwright_stealth import stealth_sync

BASE_URL = "https://www.pccomponentes.com"


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def fetch_gpus_via_category() -> dict:
    with sync_playwright() as p:
        # 1. Usamos un User-Agent real para evitar bloqueos básicos
        browser = p.chromium.launch(headless=True)

        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        )

        page = context.new_page()
        # Si usas playwright-stealth, descomenta la siguiente línea:
        # stealth_sync(page)

        # 2. Navegar y esperar a que las cookies de seguridad se asienten
        page.goto(
            f"{BASE_URL}/tarjetas-graficas",
            wait_until="networkidle",  # Esperamos a que la red descanse
            timeout=60000,
        )

        # 3. Llamada a la API usando el contexto de la página (hereda cookies)
        # Añadimos headers más realistas
        response = page.request.get(
            f"{BASE_URL}/api/articles/search",
            params={
                "channel": "es",
                "idFamily": 6,
                "page": 1,
                "pageSize": 40,
                "orderBy": "relevance",
            },
            headers={
                "referer": f"{BASE_URL}/tarjetas-graficas",
                "accept": "application/json, text/plain, */*",
                "x-requested-with": "XMLHttpRequest",  # A veces es necesario para APIs internas
            },
        )

        if not response.ok:
            # Si falla, imprimimos el error para debug
            print(f"Error detectado: {response.status}")
            return {"error": response.status, "content": response.text()}

        data = response.json()
        browser.close()

        return {
            "retailer": "pccomponentes",
            "category": "tarjetas-graficas",
            "scraped_at": _iso_now(),
            "results_count": len(data.get("articles", [])),
            "raw_response": data,
        }


if __name__ == "__main__":
    try:
        payload = fetch_gpus_via_category()
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"Error crítico: {e}")
