"""STEP D — checkpointing + human-in-the-loop interrupt/resume.

Verifies:
  - a plan can be interrupted before the assembler (commit) node,
  - the draft state (candidate_plan, verifier_issues, instructor picks)
    is inspectable while paused,
  - resuming from the checkpoint finalizes the SAME plan (state
    continuity),
  - SqliteSaver persists across separate graph instances (durable
    resume), and
  - run_multi_agent_plan still works with a checkpointer + thread_id.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from agents import multi_agent
from agents.multi_agent import graph as graph_mod


@pytest.fixture(autouse=True)
def stub(monkeypatch):
    monkeypatch.setenv("PLANNER_REACT", "0")
    in_schedule = {"CSEN 122", "ENGL 181"}
    monkeypatch.setattr(graph_mod, "tool_check_in_schedule", lambda c: c in in_schedule)
    monkeypatch.setattr(graph_mod, "tool_detect_conflicts", lambda codes: [])
    monkeypatch.setattr(graph_mod, "tool_get_lab_partner", lambda c: None)
    monkeypatch.setattr(
        graph_mod, "tool_score_double_tag_coverage",
        lambda codes, reqs: {"total_open_reqs": 0, "covered": [], "uncovered": [], "double_tag_picks": []},
    )
    monkeypatch.setattr(
        graph_mod, "tool_get_sections",
        lambda code: [{"section": 1, "instructors": [f"Prof {code[-1]}"],
                       "meeting_days": [0], "meeting_start_min": 75, "meeting_end_min": 140}]
        if code in in_schedule else [],
    )
    monkeypatch.setattr(
        graph_mod, "tool_get_instructor_rating",
        lambda name: {"instructor": name, "rating": 4.0, "difficulty": 2.0},
    )


def _stub_client(plan: dict):
    class _Models:
        def generate_content(self, model, contents, config):
            return SimpleNamespace(text=json.dumps(plan))
    return SimpleNamespace(models=_Models())


_PLAN = {"recommended": [
    {"course": "CSEN 122", "category": "Major", "units": 4, "reason": "core"},
    {"course": "ENGL 181", "category": "Core", "units": 4, "reason": "writing"},
]}


# ── checkpointer factories ───────────────────────────────────────────────────


def test_memory_checkpointer_factory():
    cp = multi_agent.make_memory_checkpointer()
    assert cp is not None


def test_sqlite_checkpointer_factory(tmp_path):
    cp = multi_agent.make_sqlite_checkpointer(str(tmp_path / "cp.db"))
    assert cp is not None
    assert (tmp_path / "cp.db").exists()


# ── interrupt + resume (in-memory) ───────────────────────────────────────────


def test_interrupt_before_assembler_then_resume(monkeypatch):
    monkeypatch.setattr(graph_mod, "get_genai_client", lambda **_: _stub_client(_PLAN))
    cp = multi_agent.make_memory_checkpointer()
    tid = "thread-1"

    # 1. Start with review — runs up to assembler, then pauses.
    review = multi_agent.start_plan_with_review(
        missing_details=[{"course": "CSEN 122", "category": "Major", "units": 4}],
        user_preference="balanced",
        thread_id=tid,
        checkpointer=cp,
    )
    assert review["interrupted"] is True
    assert review["next"] == ["assembler"], "should be paused right before commit"
    # Draft is inspectable while paused…
    draft_codes = [c["course"] for c in review["candidate_plan"]]
    assert draft_codes == ["CSEN 122", "ENGL 181"]
    # …and instructor picks already fanned out before the pause.
    assert set(review["instructor_assignments"].keys()) == {"CSEN 122", "ENGL 181"}

    # 2. Resume from the checkpoint → finalize.
    final = multi_agent.resume_plan(thread_id=tid, checkpointer=cp)
    assert [r["course"] for r in final["recommended"]] == ["CSEN 122", "ENGL 181"]
    assert final["total_units"] == 8
    # State continuity: the finalized plan matches the reviewed draft.
    assert draft_codes == [r["course"] for r in final["recommended"]]


def test_get_plan_state_reports_pause_point(monkeypatch):
    monkeypatch.setattr(graph_mod, "get_genai_client", lambda **_: _stub_client(_PLAN))
    cp = multi_agent.make_memory_checkpointer()
    tid = "thread-2"
    multi_agent.start_plan_with_review(
        missing_details=[{"course": "CSEN 122", "category": "Major", "units": 4}],
        thread_id=tid, checkpointer=cp,
    )
    state = multi_agent.get_plan_state(thread_id=tid, checkpointer=cp)
    assert state["next"] == ["assembler"]
    assert "candidate_plan" in state["values"]


# ── durable resume across graph instances (SQLite) ──────────────────────────


def test_sqlite_resume_survives_new_graph_instance(monkeypatch):
    """Simulate a process restart: start with one SqliteSaver, resume with a
    fresh saver pointed at the SAME db file."""
    monkeypatch.setattr(graph_mod, "get_genai_client", lambda **_: _stub_client(_PLAN))
    with tempfile.TemporaryDirectory() as d:
        db = str(Path(d) / "cp.db")
        tid = "thread-durable"

        cp1 = multi_agent.make_sqlite_checkpointer(db)
        review = multi_agent.start_plan_with_review(
            missing_details=[{"course": "CSEN 122", "category": "Major", "units": 4}],
            thread_id=tid, checkpointer=cp1,
        )
        assert review["interrupted"] is True

        # New checkpointer instance on the same file = "after restart".
        cp2 = multi_agent.make_sqlite_checkpointer(db)
        final = multi_agent.resume_plan(thread_id=tid, checkpointer=cp2)
        assert [r["course"] for r in final["recommended"]] == ["CSEN 122", "ENGL 181"]


# ── run_multi_agent_plan with checkpointer runs to completion ───────────────


def test_run_with_checkpointer_completes(monkeypatch):
    monkeypatch.setattr(graph_mod, "get_genai_client", lambda **_: _stub_client(_PLAN))
    cp = multi_agent.make_memory_checkpointer()
    out = multi_agent.run_multi_agent_plan(
        missing_details=[{"course": "CSEN 122", "category": "Major", "units": 4}],
        thread_id="thread-complete",
        checkpointer=cp,
    )
    # No interrupt configured here → runs straight through to a final plan.
    assert [r["course"] for r in out["recommended"]] == ["CSEN 122", "ENGL 181"]
    assert out["total_units"] == 8


def test_run_without_checkpointer_still_works(monkeypatch):
    """Backward compat: no checkpointer/thread_id → in-memory, completes."""
    monkeypatch.setattr(graph_mod, "get_genai_client", lambda **_: _stub_client(_PLAN))
    out = multi_agent.run_multi_agent_plan(
        missing_details=[{"course": "CSEN 122", "category": "Major", "units": 4}],
    )
    assert out["total_units"] == 8
