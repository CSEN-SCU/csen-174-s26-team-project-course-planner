"""Idempotent schema migration.

Runs the SQL in `schema.sql` and creates the sqlite-vec virtual table
`memory_vec`. Safe to call on every app start.

The vector dimension matches Gemini ``text-embedding-004`` (768).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

from db.connection import close_conn, get_conn, load_sqlite_vec_extension

EMBEDDING_DIM = 768
_SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def _ensure_vec_table(conn: sqlite3.Connection) -> None:
    """Create the vec0 virtual table if missing.

    `CREATE VIRTUAL TABLE IF NOT EXISTS` is supported by SQLite, but the
    sqlite-vec extension must be loaded on the connection before this runs;
    `get_conn()` guarantees that.
    """
    conn.execute(
        f"CREATE VIRTUAL TABLE IF NOT EXISTS memory_vec USING vec0(embedding float[{EMBEDDING_DIM}])"
    )


def migrate(db_path: Optional[str] = None) -> None:
    """Apply all DDL. Idempotent."""
    sql = _SCHEMA_PATH.read_text(encoding="utf-8")
    conn = get_conn(db_path)
    try:
        conn.executescript(sql)
        if load_sqlite_vec_extension(conn):
            _ensure_vec_table(conn)
        conn.commit()
    finally:
        close_conn(conn)


if __name__ == "__main__":
    migrate()
    print("Migration complete.")
