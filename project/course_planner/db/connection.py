"""SQLite connection helpers with sqlite-vec extension loading.

`get_conn()` returns a connection with foreign keys enabled and the
sqlite-vec extension loaded so that `vec0` virtual tables work.

The default DB lives at ``project/course_planner/data/app.db`` and is
gitignored. Tests pass an explicit path (typically `:memory:` is unsafe
because connections opened for tests need to share the same in-memory
database; tests use a real temp file instead).
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


def get_conn(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Open a sqlite3 connection with sqlite-vec loaded and FKs enforced."""
    path = db_path or os.environ.get("COURSE_PLANNER_DB") or default_db_path()
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
    finally:
        # Disable extension loading once the trusted extension is loaded; this
        # prevents arbitrary `load_extension()` calls from later SQL.
        try:
            conn.enable_load_extension(False)
        except sqlite3.NotSupportedError:
            pass
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def close_conn(conn: Optional[sqlite3.Connection]) -> None:
    if conn is None:
        return
    try:
        conn.close()
    except sqlite3.ProgrammingError:
        pass
