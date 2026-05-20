"""End-to-end tests for the LangGraph multi-agent planner.

We stub the Gemini client so these tests are fast and offline, but they
DO exercise the real StateGraph: node ordering, the verifier feedback
loop, and instructor enrichment.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from agents import multi_agent
from agents.multi_agent import graph as graph_mod


# ── Gemini stub ──────────────────────────────────────────────────────────────


class _StubModels:
    """Sequential reply queue — call N pops reply N."""

    def __init__(self, replies: list[dict]):
        self._replies = list(replies)
        self.calls = 0

    def generate_content(self, model, contents, config):  # noqa: D401
        self.calls += 1
        reply = self._replies[min(self.calls - 1, len(self._replies) - 1)]
        return SimpleNamespace(text=json.dumps(reply))


def _stub_client(replies: list[dict]) -> SimpleNamespace:
    models = _StubModels(replies)
    return SimpleNamespace(models=models)


# ── Tool stubs for offline determinism ───────────────────────────────────────


@pytest.fixture(autouse=True)
def stub_tools(monkeypatch):
    """All tool calls return canned data so the graph never touches xlsx
    files or Gemini."""
    # These tests exercise graph ORCHESTRATION with a simple stubbed planner
    # (graph_mod.get_genai_client). The ReAct planner lives in a separate
    # module with its own client import and is covered by
    # test_planner_react.py — so force the single-shot path here.
    monkeypatch.setenv("PLANNER_REACT", "0")

    # Schedule contains CSEN 122 + lab + ENGL 181 + ECEN 153 + lab.
    in_schedule = {"CSEN 122", "CSEN 122L", "ENGL 181", "ECEN 153", "ECEN 153L"}

    monkeypatch.setattr(graph_mod, "tool_check_in_schedule", lambda code: code in in_schedule)
    monkeypatch.setattr(graph_mod, "tool_detect_conflicts", lambda codes: [])
    monkeypatch.setattr(
        graph_mod,
        "tool_score_double_tag_coverage",
        lambda codes, reqs: {
            "total_open_reqs": len(reqs),
            "covered": [],
            "uncovered": [],
            "double_tag_picks": [],
        },
    )
    monkeypatch.setattr(graph_mod, "tool_get_lab_partner", lambda c: None)
    monkeypatch.setattr(
        graph_mod,
        "tool_get_sections",
        lambda code: [
            {
                "section": 1,
                "meeting_days": [0, 2, 4],
                "meeting_start_min": 75,
                "meeting_end_min": 140,
                "instructors": ["Weijia Shang"],
            }
        ]
        if code in in_schedule
        else [],
    )
    monkeypatch.setattr(
        graph_mod,
        "tool_compare_instructors",
        lambda names: [{"instructor": n, "rating": None} for n in names],
    )


# ── Happy path: planner produces valid plan, verifier passes, assembler emits ───


def test_happy_path_single_planner_call(monkeypatch):
    plan_reply = {
        "recommended": [
            {"course": "CSEN 122", "category": "Major", "units": 4, "reason": "core"},
            {"course": "ENGL 181", "category": "Core", "units": 4, "reason": "writing"},
        ]
    }
    stub = _stub_client([plan_reply])
    monkeypatch.setattr(graph_mod, "get_genai_client", lambda **_: stub)

    out = multi_agent.run_multi_agent_plan(
        missing_details=[{"course": "CSEN 122", "category": "Major", "units": 4}],
        user_preference="balanced",
    )

    codes = [r["course"] for r in out["recommended"]]
    assert codes == ["CSEN 122", "ENGL 181"]
    assert out["total_units"] == 8
    # Planner called once, no retry loop.
    assert stub.models.calls == 1
    # Each course got an instructor pick.
    assert all(r.get("section") for r in out["recommended"])
    assert out["recommended"][0]["section"]["instructor"] == "Weijia Shang"


# ── Verifier feedback loop: first reply is hallucinated → planner re-runs ────


def test_verifier_feeds_hallucination_back_to_planner(monkeypatch):
    bad_reply = {
        "recommended": [
            {"course": "FAKE 999", "category": "Major", "units": 4, "reason": "?"},
        ]
    }
    good_reply = {
        "recommended": [
            {"course": "CSEN 122", "category": "Major", "units": 4, "reason": "core"},
        ]
    }
    stub = _stub_client([bad_reply, good_reply])
    monkeypatch.setattr(graph_mod, "get_genai_client", lambda **_: stub)

    out = multi_agent.run_multi_agent_plan(
        missing_details=[{"course": "CSEN 122", "category": "Major", "units": 4}],
        user_preference="any",
    )

    # Planner was invoked twice: first draft + correction after verifier.
    assert stub.models.calls == 2
    # Final plan only contains the valid course.
    assert [r["course"] for r in out["recommended"]] == ["CSEN 122"]
    assert out["verifier_passes"] >= 1
    assert out["verifier_issues"] == [], "final pass must have no issues"


# ── Verifier loop is bounded — 3 hallucinated attempts → still terminates ───


def test_verifier_loop_terminates_after_retry_budget(monkeypatch):
    bad = {"recommended": [{"course": "NOT 1", "category": "X", "units": 1, "reason": "."}]}
    stub = _stub_client([bad, bad, bad, bad, bad])  # all bad
    monkeypatch.setattr(graph_mod, "get_genai_client", lambda **_: stub)

    out = multi_agent.run_multi_agent_plan(
        missing_details=[{"course": "CSEN 122", "category": "Major", "units": 4}],
        user_preference="any",
    )

    # Initial draft + 2 corrections = 3 planner calls max.
    assert stub.models.calls <= 3
    # Graph terminated (didn't hang).
    assert "recommended" in out


# ── State plumbing: previous_plan + memory_snippets reach the planner prompt ─


def test_previous_plan_and_memory_passed_through(monkeypatch):
    captured: dict = {}

    def _capture_planner(state):
        captured["state"] = state
        return {"candidate_plan": []}

    monkeypatch.setattr(graph_mod, "planner_node", _capture_planner)

    multi_agent.run_multi_agent_plan(
        missing_details=[],
        user_preference="add a core",
        previous_plan={"recommended": [{"course": "CSEN 122"}]},
        memory_snippets=["user prefers no morning classes"],
    )

    s = captured["state"]
    assert s["user_preference"] == "add a core"
    assert s["previous_plan"] == {"recommended": [{"course": "CSEN 122"}]}
    assert s["memory_snippets"] == ["user prefers no morning classes"]


# ── Graph construction sanity: graph compiles, nodes/edges are present ─────


def test_graph_compiles_with_expected_nodes():
    g = graph_mod.build_graph()
    # langgraph's compiled graph exposes `.get_graph()`
    gdef = g.get_graph()
    nodes = {n.id for n in gdef.nodes.values()}
    for needed in {"planner", "verifier", "instructor_one", "assembler"}:
        assert needed in nodes, f"missing node {needed!r}"


# ── Tool registry sanity ────────────────────────────────────────────────────


def test_tool_registry_exposes_all_tools():
    from agents.multi_agent.tools import ALL_TOOLS

    expected = {
        "search_schedule",
        "get_open_req_candidates",
        "get_lab_partner",
        "check_in_schedule",
        "detect_conflicts",
        "score_double_tag_coverage",
        "get_sections",
        "get_instructor_rating",
        "compare_instructors",
    }
    assert expected <= set(ALL_TOOLS.keys())
    # Every tool is callable.
    for name, fn in ALL_TOOLS.items():
        assert callable(fn), f"{name} not callable"
