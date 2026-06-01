from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "api"))
sys.path.insert(0, str(_ROOT / "course_planner"))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from routers import plan as plan_router  # noqa: E402


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(plan_router, "limit", lambda *_a, **_k: (lambda: None))
    app = FastAPI()
    app.include_router(plan_router.router, prefix="/api/plan")
    return TestClient(app)


def test_default_plan_always_uses_llm_selection(client, monkeypatch):
    """Old engine selector values must not route away from the LLM planner."""
    called = {"llm": False}
    monkeypatch.setattr(plan_router, "run_professor_agent", lambda recs, **kw: recs)

    def fake_llm_planner(*_args, **_kwargs):
        called["llm"] = True
        return {
            "recommended": [{"course": "CSEN 122", "units": 4}],
            "total_units": 4,
            "advice": "Take CSEN 122.",
            "assistant_reply": "I recommend CSEN 122.",
            "meta": {"validation": {"engine": "llm_select"}},
        }

    monkeypatch.setattr(plan_router, "run_llm_planner", fake_llm_planner)

    response = client.post(
        "/api/plan",
        json={
            "missing_details": [{"course": "CSEN 122", "category": "Major"}],
            "user_preference": "plan next quarter",
        },
    )

    assert response.status_code == 200
    assert called["llm"] is True
    assert response.json()["meta"]["validation"]["engine"] == "llm_select"
