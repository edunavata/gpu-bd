# src/common/db.py

import os
import sqlite3
from pathlib import Path


# Default database path (local-first)
DEFAULT_DB_PATH = Path("db/pcbuilder.db")


def get_db_path() -> Path:
    """
    Returns the SQLite database path.
    Can be overridden via the PCB_BUILDER_DB environment variable.
    """
    return Path(os.getenv("PCBUILDER_DB", DEFAULT_DB_PATH))


def get_connection() -> sqlite3.Connection:
    """
    Creates and returns a configured SQLite connection.

    The connection is configured with sane defaults for
    analytical workloads and data integrity.
    """
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    _configure_connection(conn)
    return conn


def _configure_connection(conn: sqlite3.Connection) -> None:
    """
    Applies SQLite pragmas required for correct and efficient operation.
    """
    cursor = conn.cursor()

    cursor.execute("PRAGMA foreign_keys = ON;")
    cursor.execute("PRAGMA journal_mode = WAL;")
    cursor.execute("PRAGMA synchronous = NORMAL;")

    cursor.close()
