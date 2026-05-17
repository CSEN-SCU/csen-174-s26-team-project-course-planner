"""SQLite connection helpers with optional sqlite-vec extension loading.

`get_conn()` returns a connection with foreign keys enabled. Call
``load_sqlite_vec_extension(conn)`` before using vec0 tables (see ``migrate``);
auth and per-user memory markdown do not need the extension.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Optional

import sqlite_vec

_DEFAULT_DIR = Path(__file__).resolve().parent.parent / "data"
_DEFAULT_DB = _DEFAULT_DIR / "app.db"


def default_db_path() -> str:
    """Return the on-disk default database path, creating its directory."""
    _DEFAULT_DIR.mkdir(parents=True, exist_ok=True)
    return str(_DEFAULT_DB)


def load_sqlite_vec_extension(conn: sqlite3.Connection) -> bool:
    """Load sqlite-vec on this connection when the runtime allows it."""
    enable = getattr(conn, "enable_load_extension", None)
    if enable is None:
        return False
    try:
        enable(True)
        sqlite_vec.load(conn)
    except (AttributeError, sqlite3.NotSupportedError, sqlite3.OperationalError, OSError):
        try:
            enable(False)
        except (AttributeError, sqlite3.NotSupportedError):
            pass
        return False
    try:
        enable(False)
    except (AttributeError, sqlite3.NotSupportedError):
        pass
    return True


def get_conn(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Open a sqlite3 connection with foreign keys enforced."""
    path = db_path or os.environ.get("COURSE_PLANNER_DB") or default_db_path()
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def close_conn(conn: Optional[sqlite3.Connection]) -> None:
    if conn is None:
        return
    try:
        conn.close()
    except sqlite3.ProgrammingError:
        pass
