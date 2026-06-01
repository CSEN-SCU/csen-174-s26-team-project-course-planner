"""STEP E — HTTP wiring for the multi-agent engine.

Builds a minimal FastAPI app mounting just the plan router and drives the
new endpoints with TestClient, stubbing the multi-agent functions so no
Gemini / xlsx I/O happens.

Covers:
  - POST /api/plan/v2 runs the multi-agent engine and shapes the response
  - conversational + no-transcript guards still apply on v2
  - legacy POST /api/plan delegates to multi-agent when MULTI_AGENT_PLAN=1
  - HITL: /v2/review returns a draft, /v2/resume finalizes it
  - validation: review/resume require a thread_id
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]  # project/
sys.path.insert(0, str(_ROOT / "api"))
sys.path.insert(0, str(_ROOT / "course_planner"))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from routers import plan as plan_router  # noqa: E402


@pytest.fixture
def client(monkeypatch):
    # Neutralize rate limiting so repeated test calls don't 429.
    monkeypatch.setattr(plan_router, "limit", lambda *_a, **_k: (lambda: None))
    app = FastAPI()
    app.include_router(plan_router.router, prefix="/api/plan")
    return TestClient(app)


_FAKE_PLAN = {
    "recommended": [
        {"course": "CSEN 122", "category": "Major", "units": 4, "reason": "core",
         "section": {"instructor": "Weijia Shang"}},
        {"course": "ENGL 181", "category": "Core", "units": 4, "reason": "writing",
         "section": {"instructor": "David Coad"}},
    ],
    "total_units": 8,
    "verifier_passes": 1,
    "verifier_issues": [],
}


# ── POST /api/plan/v2 ────────────────────────────────────────────────────────


def test_v2_runs_multi_agent_and_shapes_response(client, monkeypatch):
    import agents.multi_agent as ma
    monkeypatch.setattr(ma, "run_multi_agent_plan", lambda *a, **k: dict(_FAKE_PLAN))

    r = client.post("/api/plan/v2", json={
        "missing_details": [{"course": "CSEN 122", "category": "Major", "units": 4}],
        "user_preference": "balanced",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["type"] == "plan"
    assert body["engine"] == "multi_agent"
    assert [c["course"] for c in body["recommended"]] == ["CSEN 122", "ENGL 181"]
    assert body["total_units"] == 8
    # advice + assistant_reply synthesized deterministically (drop-in shape)
    assert "8-unit" in body["assistant_reply"] or "8 units" in body["advice"]
    assert "CSEN 122" in body["assistant_reply"]


def test_v2_conversational_message_short_circuits(client, monkeypatch):
    # A question should NOT invoke the planner.
    called = {"plan": False}
    import agents.multi_agent as ma

    def _should_not_run(*a, **k):
        called["plan"] = True
        return dict(_FAKE_PLAN)

    monkeypatch.setattr(ma, "run_multi_agent_plan", _should_not_run)
    monkeypatch.setattr(plan_router, "_answer_conversational", lambda *a, **k: "Hi! Ask away.")

    r = client.post("/api/plan/v2", json={
        "missing_details": [{"course": "CSEN 122"}],
        "user_preference": "what is a unit cap?",
    })
    assert r.status_code == 200
    assert r.json()["type"] == "answer"
    assert called["plan"] is False


def test_v2_no_transcript_asks_to_upload(client):
    r = client.post("/api/plan/v2", json={"missing_details": [], "user_preference": "plan me"})
    assert r.status_code == 200
    assert r.json()["type"] == "answer"
    assert "upload" in r.json()["reply"].lower()


def test_v2_agent_failure_returns_502(client, monkeypatch):
    import agents.multi_agent as ma

    def _boom(*a, **k):
        raise RuntimeError("graph exploded")

    monkeypatch.setattr(ma, "run_multi_agent_plan", _boom)
    r = client.post("/api/plan/v2", json={
        "missing_details": [{"course": "CSEN 122"}],
        "user_preference": "plan",
    })
    assert r.status_code == 502


# ── legacy delegation flag ───────────────────────────────────────────────────


def test_legacy_plan_delegates_when_flag_enabled(client, monkeypatch):
    monkeypatch.setattr(plan_router, "_MULTI_AGENT_DEFAULT", True)
    import agents.multi_agent as ma
    monkeypatch.setattr(ma, "run_multi_agent_plan", lambda *a, **k: dict(_FAKE_PLAN))

    r = client.post("/api/plan", json={
        "missing_details": [{"course": "CSEN 122"}],
        "user_preference": "plan",
    })
    assert r.status_code == 200
    assert r.json()["engine"] == "multi_agent"  # came through the multi-agent path


def test_default_plan_ignores_major_kwarg_for_engine_without_support(client, monkeypatch):
    """Confirmed major should not crash older constrained planner signatures."""
    monkeypatch.setattr(plan_router, "_MULTI_AGENT_DEFAULT", False)
    monkeypatch.setattr(plan_router, "_PLAN_ENGINE", "constrained_v2")
    monkeypatch.setattr(plan_router, "run_professor_agent", lambda recs, **kw: recs)

    def _old_constrained_planner(
        missing_details,
        user_preference,
        *,
        memory_snippets=None,
        previous_plan=None,
        parsed_rows=None,
        completed_course_codes=None,
    ):
        return dict(_FAKE_PLAN)

    monkeypatch.setattr(plan_router, "run_constrained_planner", _old_constrained_planner)

    r = client.post("/api/plan", json={
        "missing_details": [{"course": "CSEN 122"}],
        "user_preference": "generate a schedule",
        "student_major_id": "csen",
    })

    assert r.status_code == 200
    assert r.json()["type"] == "plan"
    assert [c["course"] for c in r.json()["recommended"]] == ["CSEN 122", "ENGL 181"]


# ── HITL review + resume ─────────────────────────────────────────────────────


def test_review_returns_draft(client, monkeypatch):
    import agents.multi_agent as ma
    monkeypatch.setattr(
        ma, "start_plan_with_review",
        lambda *a, **k: {
            "interrupted": True,
            "next": ["assembler"],
            "candidate_plan": [{"course": "CSEN 122"}],
            "verifier_issues": [],
            "instructor_assignments": {"CSEN 122": {"instructor": "Weijia Shang"}},
        },
    )
    r = client.post("/api/plan/v2/review", json={
        "missing_details": [{"course": "CSEN 122"}],
        "thread_id": "t1",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["type"] == "plan_review"
    assert body["interrupted"] is True
    assert body["next"] == ["assembler"]


def test_review_requires_thread_id(client):
    r = client.post("/api/plan/v2/review", json={"missing_details": [{"course": "X"}]})
    assert r.status_code == 400


def test_review_requires_transcript(client):
    r = client.post("/api/plan/v2/review", json={"missing_details": [], "thread_id": "t1"})
    assert r.status_code == 400


def test_resume_finalizes(client, monkeypatch):
    import agents.multi_agent as ma
    monkeypatch.setattr(ma, "resume_plan", lambda *a, **k: dict(_FAKE_PLAN))
    r = client.post("/api/plan/v2/resume", json={"thread_id": "t1"})
    assert r.status_code == 200
    body = r.json()
    assert body["engine"] == "multi_agent"
    assert body["total_units"] == 8


def test_resume_requires_thread_id(client):
    r = client.post("/api/plan/v2/resume", json={})
    assert r.status_code == 400


# ── response shaper unit ─────────────────────────────────────────────────────


def test_shape_v2_response_synthesizes_fields():
    out = plan_router._shape_v2_response(_FAKE_PLAN)
    assert out["type"] == "plan"
    assert out["total_units"] == 8
    assert out["advice"]
    assert out["assistant_reply"]


def test_shape_v2_response_empty_plan():
    out = plan_router._shape_v2_response({"recommended": [], "total_units": 0})
    assert out["recommended"] == []
    assert "couldn't find" in out["assistant_reply"].lower()
