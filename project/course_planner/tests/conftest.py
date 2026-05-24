"""Pytest configuration for course_planner/tests/.

Sets up the import path so that ``agents``, ``auth``, ``db``, ``routers``,
and ``utils`` are all importable as top-level packages (mirroring how the API
process runs).

Also resets the rate-limiter singleton before every test so tests that route
through the FastAPI plan router don't exhaust the shared in-memory token-bucket
and cause spurious 429 responses in later tests.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_THIS_DIR = Path(__file__).resolve().parent
_CP_DIR = _THIS_DIR.parent          # course_planner/
_PROJECT_ROOT = _CP_DIR.parent      # project/
_API_ROOT = _PROJECT_ROOT / "api"

for _p in (_CP_DIR, _API_ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Give every test a pristine rate-limiter bucket so accumulated hits from
    earlier tests can't trigger 429 on plan-route requests."""
    try:
        from middleware.rate_limit import RateLimiter, set_limiter
        set_limiter(RateLimiter())
    except ImportError:
        pass
    yield
