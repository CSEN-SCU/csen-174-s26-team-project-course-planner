from __future__ import annotations

import importlib
import sys
from pathlib import Path

from fastapi.testclient import TestClient


def test_api_startup_migrates_database_before_auth_routes(tmp_path, monkeypatch):
    """Render starts uvicorn directly, so the API must prepare its own DB."""
    api_dir = Path(__file__).resolve().parents[1] / "api"
    if str(api_dir) not in sys.path:
        sys.path.insert(0, str(api_dir))

    monkeypatch.setenv("COURSE_PLANNER_DB", str(tmp_path / "startup.db"))
    monkeypatch.setenv("COURSE_PLANNER_MEMORY_DIR", str(tmp_path / "memory"))

    sys.modules.pop("main", None)
    main = importlib.import_module("main")

    with TestClient(main.app) as client:
        res = client.delete("/api/auth/user/1/data")

    assert res.status_code == 404
    assert res.json() == {"detail": "User not found."}


def test_only_google_oauth_routes_are_exposed(tmp_path, monkeypatch):
    api_dir = Path(__file__).resolve().parents[1] / "api"
    if str(api_dir) not in sys.path:
        sys.path.insert(0, str(api_dir))

    monkeypatch.setenv("COURSE_PLANNER_DB", str(tmp_path / "startup.db"))
    monkeypatch.setenv("COURSE_PLANNER_MEMORY_DIR", str(tmp_path / "memory"))

    sys.modules.pop("main", None)
    main = importlib.import_module("main")

    with TestClient(main.app) as client:
        paths = set(client.get("/openapi.json").json()["paths"])

    assert paths & {"/api/auth/google/start", "/api/auth/google/callback", "/api/auth/google/exchange"}
    assert {
        path
        for path in paths
        if path.startswith("/api/auth/") and not path.startswith("/api/auth/google/")
    } == {"/api/auth/user/{user_id}/data"}
