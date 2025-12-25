# src/common/migrate.py
import sqlite3
from pathlib import Path
from src.common.db import get_connection

SCHEMA_ROOT = Path("db/schema")


def apply_schema(conn, layer: str):
    """
    Aplica los archivos SQL de una capa.
    Continúa con el siguiente archivo si uno falla (ej. por constraints de duplicados).
    """
    layer_path = SCHEMA_ROOT / layer
    if not layer_path.exists():
        print(f"[*] La capa '{layer}' no existe en {layer_path}")
        return

    print(f"[*] Aplicando capa: {layer.upper()}")
    # Ordenamos alfabéticamente para respetar la numeración (001, 002...)
    for sql_file in sorted(layer_path.rglob("*.sql")):
        print(f"    - Ejecutando {sql_file.name}...", end="", flush=True)
        try:
            sql_content = sql_file.read_text()
            # Usamos executescript para manejar múltiples sentencias por archivo
            conn.executescript(sql_content)
            print(" [OK]")
        except sqlite3.Error as e:
            # Capturamos el error pero permitimos que el script siga adelante
            print(f" [AVISO/ERROR] {e}")


def migrate():
    conn = get_connection()
    try:
        # Aplicamos Silver primero, luego Gold
        apply_schema(conn, "silver")
        apply_schema(conn, "gold")
        conn.commit()
        print("[!] Migración finalizada.")
    except Exception as e:
        print(f"[FATAL] Error inesperado: {e}")
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
