"""POST /api/courses/refresh — catalog cache invalidation (prototype, no auth).

The catalog list is memoized at process scope (`_cached_courses`), so a
replaced schedule xlsx would otherwise require a server restart. /refresh
drops that cache plus the lru_cache loaders in scu_course_schedule_xlsx so the
next read reflects new data.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

from fastapi.testclient import TestClient

_API_DIR = Path(__file__).resolve().parents[1] / "api"


def _load_api_main(monkeypatch, tmp_path):
    if str(_API_DIR) not in sys.path:
        sys.path.insert(0, str(_API_DIR))
    monkeypatch.setenv("COURSE_PLANNER_DB", str(tmp_path / "courses.db"))
    monkeypatch.setenv("COURSE_PLANNER_MEMORY_DIR", str(tmp_path / "memory"))
    sys.modules.pop("main", None)
    return importlib.import_module("main")


# ── behaviour: refresh drops the cache so an updated xlsx is served ───────────


def test_refresh_invalidates_catalog_cache(monkeypatch, tmp_path):
    main = _load_api_main(monkeypatch, tmp_path)
    import routers.courses as courses

    # Stub the catalog source and seed the cache with a one-row list.
    catalog = [{"course": "AAA 1"}]
    monkeypatch.setattr(courses, "list_offered_courses", lambda: list(catalog))
    courses._cached_courses.cache_clear()

    try:
        with TestClient(main.app) as client:
            assert client.get("/api/courses").json()["count"] == 1

            # Underlying catalog grows, but the cache still serves the old count.
            catalog.append({"course": "BBB 2"})
            assert client.get("/api/courses").json()["count"] == 1

            # Refresh drops the cache; the next read reflects the new catalog.
            resp = client.post("/api/courses/refresh")
            assert resp.status_code == 200
            body = resp.json()
            assert body["refreshed"] is True
            assert body["count"] == 2

            assert client.get("/api/courses").json()["count"] == 2
    finally:
        # Don't leak the stubbed catalog into other tests sharing this lru_cache.
        courses._cached_courses.cache_clear()


# ── unit: scu_course_schedule_xlsx.clear_caches resets its lru_caches ─────────


def test_schedule_clear_caches_resets_lru():
    from utils import scu_course_schedule_xlsx as sx

    sx.load_instructor_ratings()
    sx.load_core_integrations_course_set()
    assert sx.load_instructor_ratings.cache_info().currsize == 1
    assert sx.load_core_integrations_course_set.cache_info().currsize == 1

    sx.clear_caches()

    assert sx.load_instructor_ratings.cache_info().currsize == 0
    assert sx.load_core_integrations_course_set.cache_info().currsize == 0
