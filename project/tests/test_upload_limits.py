from __future__ import annotations

import importlib
import sys
from pathlib import Path

from fastapi.testclient import TestClient


def test_transcript_upload_rejects_files_over_5mb(tmp_path, monkeypatch):
    api_dir = Path(__file__).resolve().parents[1] / "api"
    if str(api_dir) not in sys.path:
        sys.path.insert(0, str(api_dir))

    monkeypatch.setenv("COURSE_PLANNER_DB", str(tmp_path / "upload_limit.db"))
    monkeypatch.setenv("COURSE_PLANNER_MEMORY_DIR", str(tmp_path / "memory"))

    sys.modules.pop("main", None)
    main = importlib.import_module("main")

    oversized = b"x" * (5 * 1024 * 1024 + 1)
    with TestClient(main.app) as client:
        res = client.post(
            "/api/upload/transcript",
            files={
                "file": (
                    "Academic_Progress.xlsx",
                    oversized,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
            data={"user_id": "1"},
        )

    assert res.status_code == 413
    assert res.json().get("detail") == "File too large. Max upload size is 5 MB."
