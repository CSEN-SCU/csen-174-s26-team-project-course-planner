"""Pytest config: import as if running from `project/course_planner/`.

The Streamlit app is launched with `cwd=project/course_planner`, which
makes `agents`, `auth`, `db`, and `utils` top-level imports. Tests mirror
that path setup so test code can `from auth import users_db` etc.

Each test gets a fresh tempfile-backed SQLite database that:

- Has the schema applied via `db.migrate.migrate()`.
- Is reachable via `COURSE_PLANNER_DB` env var, so any code using
  `db.get_conn()` without an explicit path picks it up.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_APP_ROOT = Path(__file__).resolve().parents[1]  # project/course_planner/
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))


@pytest.fixture()
def db_path(tmp_path, monkeypatch):
    """Provide a fresh SQLite path and migrate it once."""
    path = tmp_path / "test_app.db"
    mem = tmp_path / "memory"
    mem.mkdir()
    monkeypatch.setenv("COURSE_PLANNER_DB", str(path))
    monkeypatch.setenv("COURSE_PLANNER_MEMORY_DIR", str(mem))
    from db.migrate import migrate

    migrate(str(path))
    yield str(path)
