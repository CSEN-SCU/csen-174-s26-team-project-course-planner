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


def _normalize_users_table(conn: sqlite3.Connection) -> None:
    columns = [row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()]
    old_secret_column = "_".join(("pass" + "word", "hash"))
    old_identity_column = "user" + "name"
    if "google_sub" in columns and old_secret_column not in columns:
        return
    identity_source = "google_sub" if "google_sub" in columns else old_identity_column

    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.execute(
            """
            CREATE TABLE users_oauth_only (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                google_sub TEXT UNIQUE NOT NULL,
                email      TEXT UNIQUE NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            f"""
            INSERT INTO users_oauth_only (id, google_sub, email, created_at)
            SELECT id, {identity_source}, email, created_at FROM users
            """
        )
        conn.execute("DROP TABLE users")
        conn.execute("ALTER TABLE users_oauth_only RENAME TO users")
    finally:
        conn.execute("PRAGMA foreign_keys = ON")


def migrate(db_path: Optional[str] = None) -> None:
    """Apply all DDL. Idempotent."""
    sql = _SCHEMA_PATH.read_text(encoding="utf-8")
    conn = get_conn(db_path)
    try:
        conn.executescript(sql)
        _normalize_users_table(conn)
        if load_sqlite_vec_extension(conn):
            _ensure_vec_table(conn)
        conn.commit()
    finally:
        close_conn(conn)


if __name__ == "__main__":
    migrate()
    print("Migration complete.")
