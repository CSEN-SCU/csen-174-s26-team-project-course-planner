"""POST /api/courses/refresh clears the catalog lru_cache."""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.main import app
from api.routers import courses as courses_router


def test_courses_refresh_returns_ok_and_count():
    courses_router._cached_courses.cache_clear()
    client = TestClient(app)
    before = client.get("/api/courses").json()["count"]
    refreshed = client.post("/api/courses/refresh")
    assert refreshed.status_code == 200
    body = refreshed.json()
    assert body["ok"] is True
    assert body["count"] == before
    after = client.get("/api/courses").json()["count"]
    assert after == before
