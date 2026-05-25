"""API tests for headed Workday pull (Playwright mocked)."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

from fastapi.testclient import TestClient


def _client(monkeypatch, *, db_path: str, memory_dir: str) -> TestClient:
    api_dir = Path(__file__).resolve().parents[1] / "api"
    if str(api_dir) not in sys.path:
        sys.path.insert(0, str(api_dir))
    monkeypatch.setenv("COURSE_PLANNER_DB", db_path)
    monkeypatch.setenv("COURSE_PLANNER_MEMORY_DIR", memory_dir)
    monkeypatch.setenv("SCU_WORKDAY_PULL_ENABLED", "1")
    sys.modules.pop("main", None)
    main = importlib.import_module("main")
    return TestClient(main.app)


def _memory_dir(db_path: str) -> str:
    return str(Path(db_path).parent / "memory")


def test_workday_available_when_enabled(db_path, monkeypatch):
    monkeypatch.setenv("SCU_WORKDAY_PULL_ENABLED", "1")
    with _client(monkeypatch, db_path=db_path, memory_dir=_memory_dir(db_path)) as client:
        res = client.get("/api/workday/available")
    assert res.status_code == 200
    assert res.json()["available"] is True


def test_sync_requires_auth(db_path, monkeypatch):
    with _client(monkeypatch, db_path=db_path, memory_dir=_memory_dir(db_path)) as client:
        res = client.post("/api/workday/sync", json={"user_id": ""})
    assert res.status_code == 401


def test_sync_and_status_scoped_to_user(db_path, monkeypatch):
    import sqlite3

    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO users (google_sub, email) VALUES (?, ?), (?, ?)",
        (
            "sub-workday-a",
            "workday-a@scu.edu",
            "sub-workday-b",
            "workday-b@scu.edu",
        ),
    )
    conn.commit()
    uid = str(conn.execute("SELECT id FROM users WHERE email = ?", ("workday-a@scu.edu",)).fetchone()[0])
    other_uid = str(
        conn.execute("SELECT id FROM users WHERE email = ?", ("workday-b@scu.edu",)).fetchone()[0]
    )
    conn.close()

    def fake_pull(user_id: str, *, progress_cb=None, manual_login=False, profile_dir=None):
        if progress_cb:
            progress_cb("parsing")
        return {
            "missing_details": [{"requirement": "RTC 1"}],
            "parsed_rows": [{"course_code": "CSEN 10", "status": "Satisfied"}],
        }

    import scripts.workday_pull_progress as wpp

    monkeypatch.setattr(wpp, "pull_academic_progress", fake_pull)

    with _client(monkeypatch, db_path=db_path, memory_dir=_memory_dir(db_path)) as client:
        start = client.post("/api/workday/sync", json={"user_id": uid})
        assert start.status_code == 200
        job_id = start.json()["job_id"]

        import time

        for _ in range(30):
            st = client.get(f"/api/workday/status/{job_id}", params={"user_id": uid})
            assert st.status_code == 200
            body = st.json()
            if body["status"] in ("done", "error"):
                break
            time.sleep(0.05)
        else:
            raise AssertionError("job did not finish")

        assert body["status"] == "done"
        assert len(body.get("parsed_rows") or []) == 1

        other = client.get(f"/api/workday/status/{job_id}", params={"user_id": other_uid})
        assert other.status_code == 404


def test_sync_sections_requires_auth(db_path, monkeypatch):
    with _client(monkeypatch, db_path=db_path, memory_dir=_memory_dir(db_path)) as client:
        res = client.post("/api/workday/sync-sections", json={"user_id": ""})
    assert res.status_code == 401


def test_sync_sections_reports_catalog_count(db_path, monkeypatch):
    import sqlite3

    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO users (google_sub, email) VALUES (?, ?)",
        ("sub-sections-a", "sections-a@scu.edu"),
    )
    conn.commit()
    uid = str(
        conn.execute("SELECT id FROM users WHERE email = ?", ("sections-a@scu.edu",)).fetchone()[0]
    )
    conn.close()

    def fake_pull(*, progress_cb=None, **kwargs):
        if progress_cb:
            progress_cb("writing")
        return {"count": 5, "term": "Fall 2026", "level": "Undergraduate"}

    import scripts.workday_pull_sections as wps

    monkeypatch.setattr(wps, "pull_course_sections", fake_pull)

    with _client(monkeypatch, db_path=db_path, memory_dir=_memory_dir(db_path)) as client:
        start = client.post("/api/workday/sync-sections", json={"user_id": uid})
        assert start.status_code == 200
        job_id = start.json()["job_id"]

        import time

        for _ in range(30):
            st = client.get(f"/api/workday/status/{job_id}", params={"user_id": uid})
            assert st.status_code == 200
            body = st.json()
            if body["status"] in ("done", "error"):
                break
            time.sleep(0.05)
        else:
            raise AssertionError("job did not finish")

        assert body["status"] == "done", body
        assert body.get("count") == 5
        assert body.get("term") == "Fall 2026"
