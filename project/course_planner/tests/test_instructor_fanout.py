"""STEP C — parallel InstructorSelector fan-out via the Send API.

Verifies that the verifier_router dispatches one ``instructor_one`` per
recommended course, that all results merge into ``instructor_assignments``
via the reducer, and that the join at ``assembler`` sees every pick.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from langgraph.types import Send

from agents import multi_agent
from agents.multi_agent import graph as graph_mod


# ── Offline stubs ────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def stub(monkeypatch):
    monkeypatch.setenv("PLANNER_REACT", "0")
    in_schedule = {"CSEN 122", "ENGL 181", "ECEN 153"}
    monkeypatch.setattr(graph_mod, "tool_check_in_schedule", lambda c: c in in_schedule)
    monkeypatch.setattr(graph_mod, "tool_detect_conflicts", lambda codes: [])
    monkeypatch.setattr(graph_mod, "tool_get_lab_partner", lambda c: None)
    monkeypatch.setattr(
        graph_mod, "tool_score_double_tag_coverage",
        lambda codes, reqs: {"total_open_reqs": 0, "covered": [], "uncovered": [], "double_tag_picks": []},
    )
    # Each course resolves to a distinct instructor so we can tell them apart.
    sections = {
        "CSEN 122": [{"section": 1, "instructors": ["Prof A"], "meeting_days": [0], "meeting_start_min": 75, "meeting_end_min": 140}],
        "ENGL 181": [{"section": 1, "instructors": ["Prof B"], "meeting_days": [1], "meeting_start_min": 30, "meeting_end_min": 130}],
        "ECEN 153": [{"section": 1, "instructors": ["Prof C"], "meeting_days": [2], "meeting_start_min": 75, "meeting_end_min": 140}],
    }
    monkeypatch.setattr(graph_mod, "tool_get_sections", lambda code: sections.get(code, []))
    monkeypatch.setattr(
        graph_mod, "tool_get_instructor_rating",
        lambda name: {"instructor": name, "rating": 4.0, "difficulty": 2.0},
    )


def _stub_client(plan: dict):
    class _Models:
        def generate_content(self, model, contents, config):
            return SimpleNamespace(text=json.dumps(plan))
    return SimpleNamespace(models=_Models())


# ── verifier_router fan-out shape ────────────────────────────────────────────


def test_router_emits_one_send_per_course():
    state = {
        "verifier_issues": [],
        "verifier_passes": 1,
        "candidate_plan": [
            {"course": "CSEN 122"}, {"course": "ENGL 181"}, {"course": "ECEN 153"},
        ],
    }
    result = graph_mod.verifier_router(state)
    assert isinstance(result, list)
    assert all(isinstance(s, Send) for s in result)
    assert len(result) == 3
    dispatched = {s.arg["course_code"] for s in result}
    assert dispatched == {"CSEN 122", "ENGL 181", "ECEN 153"}
    # Each Send targets the instructor_one node.
    assert all(s.node == "instructor_one" for s in result)


def test_router_loops_back_to_planner_when_issues_remain():
    state = {"verifier_issues": [{"type": "hallucinated"}], "verifier_passes": 1,
             "candidate_plan": [{"course": "CSEN 122"}]}
    assert graph_mod.verifier_router(state) == "planner"


def test_router_skips_to_assembler_when_no_courses():
    state = {"verifier_issues": [], "verifier_passes": 1, "candidate_plan": []}
    assert graph_mod.verifier_router(state) == "assembler"


def test_router_stops_looping_after_budget_even_with_issues():
    state = {"verifier_issues": [{"type": "x"}], "verifier_passes": 3,
             "candidate_plan": [{"course": "CSEN 122"}]}
    result = graph_mod.verifier_router(state)
    # Budget exhausted → fan out instead of looping.
    assert isinstance(result, list)
    assert result[0].arg["course_code"] == "CSEN 122"


# ── instructor_one node in isolation ─────────────────────────────────────────


def test_instructor_one_resolves_single_course():
    out = graph_mod.instructor_one_node({"course_code": "ENGL 181"})
    assert "ENGL 181" in out["instructor_assignments"]
    assert out["instructor_assignments"]["ENGL 181"]["instructor"] == "Prof B"


def test_instructor_one_empty_code_returns_empty():
    assert graph_mod.instructor_one_node({"course_code": ""}) == {}
    assert graph_mod.instructor_one_node({}) == {}


# ── End-to-end through the compiled graph ────────────────────────────────────


def test_fanout_merges_all_instructor_assignments(monkeypatch):
    plan = {"recommended": [
        {"course": "CSEN 122", "category": "Major", "units": 4, "reason": "core"},
        {"course": "ENGL 181", "category": "Core", "units": 4, "reason": "writing"},
        {"course": "ECEN 153", "category": "Major", "units": 4, "reason": "ee"},
    ]}
    monkeypatch.setattr(graph_mod, "get_genai_client", lambda **_: _stub_client(plan))

    out = multi_agent.run_multi_agent_plan(
        missing_details=[{"course": "CSEN 122", "category": "Major", "units": 4}],
        user_preference="balanced",
    )

    # Every course got its instructor pick merged in (the whole point of
    # the Send reducer fan-out).
    by_code = {r["course"]: r for r in out["recommended"]}
    assert by_code["CSEN 122"]["section"]["instructor"] == "Prof A"
    assert by_code["ENGL 181"]["section"]["instructor"] == "Prof B"
    assert by_code["ECEN 153"]["section"]["instructor"] == "Prof C"
    assert out["total_units"] == 12


def test_merge_reducer_accumulates_parallel_results():
    """The _merge_dicts reducer must combine, not clobber, partial results."""
    merged = graph_mod._merge_dicts({"A": {"x": 1}}, {"B": {"y": 2}})
    assert merged == {"A": {"x": 1}, "B": {"y": 2}}
    # Right side wins on key collision (last-write).
    assert graph_mod._merge_dicts({"A": 1}, {"A": 2}) == {"A": 2}
