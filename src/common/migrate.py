# src/common/migrate.py

from pathlib import Path
from src.common.db import get_connection


SCHEMA_ROOT = Path("db/schema")


def apply_schema(conn, layer: str):
    """
    Applies all SQL schema files for a given layer (silver or gold)
    in lexicographical order.
    """
    layer_path = SCHEMA_ROOT / layer

    for sql_file in sorted(layer_path.rglob("*.sql")):
        sql = sql_file.read_text()
        conn.executescript(sql)


def migrate():
    conn = get_connection()
    try:
        apply_schema(conn, "silver")
        apply_schema(conn, "gold")
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
