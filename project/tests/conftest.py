"""Pytest config: import as if running from `project/course_planner/`.

The FastAPI service runs with `project/course_planner/` on `sys.path`,
making `agents`, `auth`, `db`, and `utils` top-level imports. Tests
mirror that path setup so test code can `from auth import users_db` etc.

Each test gets a fresh tempfile-backed SQLite database that:

- Has the schema applied via `db.migrate.migrate()`.
- Is reachable via `COURSE_PLANNER_DB` env var, so any code using
  `db.get_conn()` without an explicit path picks it up.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_TESTS_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _TESTS_DIR.parent
_APP_ROOT = _PROJECT_ROOT / "course_planner"
_API_ROOT = _PROJECT_ROOT / "api"
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))
if str(_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_TESTS_DIR))

_API_DIR = _PROJECT_ROOT / "api"
if str(_API_DIR) not in sys.path:
    sys.path.insert(0, str(_API_DIR))


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Reset the global rate-limiter before every test (shared IP bucket across TestClient)."""
    try:
        from middleware.rate_limit import RateLimiter, RouteLimits, set_limiter

        generous = RouteLimits(
            per_minute_ip=10_000,
            per_minute_user=10_000,
            max_concurrent_per_user=100,
        )
        set_limiter(
            RateLimiter(
                limits={
                    "plan": generous,
                    "four_year_plan": generous,
                    "slot_suggest": generous,
                    "workday_sync": generous,
                }
            )
        )
    except ImportError:
        pass
    yield
    try:
        from middleware.rate_limit import RateLimiter, set_limiter

        set_limiter(RateLimiter())
    except ImportError:
        pass


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "requires_schedule_xlsx: needs project/course_planner/SCU_Find_Course_Sections.xlsx",
    )


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
