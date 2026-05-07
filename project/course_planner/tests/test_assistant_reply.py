"""Chat-style assistant reply contract.

The planning agent must:

1. Accept a ``previous_plan`` argument and surface a compact view of it in
   the prompt so the model can diff against it.
2. Instruct the model to fill an ``assistant_reply`` field that directly
   answers the student's preference message in first person, including
   what was added/kept/removed and why.
3. Pass ``assistant_reply`` straight through to the caller's dict.
4. When wired through ``orchestrator.plan_for_user``, the previous plan
   the UI already has on screen must be forwarded into the agent.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from agents import orchestrator, planning_agent
from auth import users_db


def _stub_client(captured_prompts: list[str], reply: dict):
    class _Models:
        def generate_content(self, model, contents, config):  # noqa: D401
            captured_prompts.append(contents)
            return SimpleNamespace(text=json.dumps(reply))

    class _Client:
        models = _Models()

    return _Client()


@pytest.fixture()
def alice(db_path):
    return users_db.create_user(
        "alice", "alice@example.com", "correct horse battery", db_path=db_path
    )


def test_previous_plan_is_summarized_into_prompt(monkeypatch):
    captured: list[str] = []
    reply = {
        "recommended": [{"course": "CSEN 161", "category": "Core", "units": 4, "reason": "core"}],
        "total_units": 4,
        "advice": "ok",
        "assistant_reply": "Yes, I added CSEN 161 because it stayed under your unit cap.",
    }
    monkeypatch.setattr(planning_agent, "_get_client", lambda: _stub_client(captured, reply))

    previous_plan = {
        "recommended": [
            {"course": "CSEN 194", "category": "Senior Design", "units": 4, "reason": "kickoff"},
            {"course": "ECEN 153", "category": "Major Tech", "units": 4, "reason": "ELEN core"},
        ],
        "total_units": 16,
        "advice": "Balanced first cut.",
    }

    result = planning_agent.run_planning_agent(
        missing_details=[{"course": "CSEN 161", "category": "Core", "units": 4}],
        user_preference="is it possible to add another core class?",
        previous_plan=previous_plan,
    )

    prompt = captured[0]
    assert "CURRENT STATE" in prompt
    assert "CSEN 194" in prompt
    assert "ECEN 153" in prompt
    assert "FOLLOW-UP" in prompt or "follow-up" in prompt.lower()
    assert "CURRENT ASK" in prompt
    # assistant_reply round-trips intact
    assert result["assistant_reply"].startswith("Yes,")


def test_no_previous_plan_uses_initial_summary_instruction(monkeypatch):
    captured: list[str] = []
    reply = {
        "recommended": [],
        "total_units": 0,
        "advice": "ok",
        "assistant_reply": "Here is a balanced first cut for next quarter.",
    }
    monkeypatch.setattr(planning_agent, "_get_client", lambda: _stub_client(captured, reply))

    planning_agent.run_planning_agent(
        missing_details=[{"course": "CSEN 161", "category": "Core", "units": 4}],
        user_preference="under 16 units, mornings only",
        previous_plan=None,
    )

    prompt = captured[0]
    assert "CURRENT STATE" not in prompt
    assert "FOLLOW-UP" not in prompt
    assert "summarise in first person" in prompt or "first person" in prompt


def test_orchestrator_forwards_previous_plan(monkeypatch, alice):
    """The UI's most-recent plan must reach the planning agent."""
    captured_kwargs: dict = {}

    def fake_run_planning_agent(**kwargs):
        captured_kwargs.update(kwargs)
        return {
            "recommended": [],
            "total_units": 0,
            "advice": "x",
            "assistant_reply": "no change",
        }

    monkeypatch.setattr(orchestrator, "run_planning_agent", fake_run_planning_agent)

    previous = {
        "recommended": [{"course": "CSEN 194", "category": "Senior Design", "units": 4, "reason": "kickoff"}],
        "total_units": 4,
        "advice": "first plan",
    }

    orchestrator.plan_for_user(
        alice,
        [{"course": "CSEN 194", "category": "Senior Design", "units": 4}],
        "swap CSEN 194 for next quarter",
        previous_plan=previous,
    )

    assert captured_kwargs.get("previous_plan") is previous


def test_reduce_units_followup_prompt_isolates_current_ask(monkeypatch, alice):
    """Real-world regression: previous plan was 24 units, history (memory)
    contains an older 'add another 4 units' preference, and the CURRENT
    ASK is 'limit under 20 units'. The prompt must:

    - Frame memory as BACKGROUND CONTEXT, not as instructions.
    - Carry the previous 24-unit plan as CURRENT STATE (the diff baseline).
    - Make CURRENT ASK the only instruction the model is told to honour.
    - Tell the model to drop courses to satisfy the unit cap.

    Without this framing the model conflates the older 'add 4 units'
    preference with the new 'reduce' ask and produces a contradictory reply.
    """
    from agents import memory_agent

    memory_agent.write(alice, "preference", "is it possible to add another 4 units to original plan")
    memory_agent.write(alice, "plan_outcome",
                       "PREF: is it possible to add another 4 units to original plan\n"
                       "GAP: CSEN 194, ECEN 153, CSEN 122, PHIL 11, ENGL 181\n"
                       "PLAN: CSEN 194, ECEN 153, CSEN 122, PHIL 11, ENGL 181 | total_units=24")

    captured: list[str] = []
    reply = {
        "recommended": [
            {"course": "CSEN 194", "category": "Senior Design", "units": 4, "reason": "kickoff"},
            {"course": "ECEN 153", "category": "Major Tech", "units": 4, "reason": "ELEN core"},
            {"course": "PHIL 11", "category": "Core", "units": 4, "reason": "core"},
            {"course": "ENGL 181", "category": "Core", "units": 4, "reason": "core"},
        ],
        "total_units": 16,
        "advice": "ok",
        "assistant_reply": "Yes, removed: CSEN 122. Plan now has CSEN 194, ECEN 153, PHIL 11, ENGL 181 — total_units=16, under your 20-unit cap.",
    }
    monkeypatch.setattr(planning_agent, "_get_client", lambda: _stub_client(captured, reply))

    previous_plan = {
        "recommended": [
            {"course": "CSEN 194", "category": "Senior Design", "units": 4, "reason": "kickoff"},
            {"course": "ECEN 153", "category": "Major Tech", "units": 4, "reason": "ELEN core"},
            {"course": "CSEN 122", "category": "Major Tech", "units": 4, "reason": "OS"},
            {"course": "PHIL 11", "category": "Core", "units": 4, "reason": "core"},
            {"course": "ENGL 181", "category": "Core", "units": 4, "reason": "core"},
            {"course": "ENGR 111", "category": "Core", "units": 4, "reason": "core"},
        ],
        "total_units": 24,
    }

    orchestrator.plan_for_user(
        alice,
        [{"course": "CSEN 194", "category": "Senior Design", "units": 4}],
        "with my latest schedule limit unit under 20 units",
        previous_plan=previous_plan,
    )

    prompt = captured[0]

    bg_idx = prompt.index("=== BACKGROUND CONTEXT")
    cs_idx = prompt.index("=== CURRENT STATE")
    ca_idx = prompt.index("=== CURRENT ASK")
    assert bg_idx < cs_idx < ca_idx, (
        "Section ordering must be BACKGROUND -> CURRENT STATE -> CURRENT ASK so "
        "the model treats history as background and only the ASK as instruction."
    )

    bg_block = prompt[bg_idx:cs_idx]
    assert "NOT current instructions" in bg_block
    assert "CURRENT ASK\n        wins" in bg_block or "CURRENT ASK wins" in bg_block

    cs_block = prompt[cs_idx:ca_idx]
    assert "total_units = 24" in cs_block
    assert "CSEN 194" in cs_block
    assert "CSEN 122" in cs_block

    ca_block = prompt[ca_idx:]
    assert "limit unit under 20 units" in ca_block
    assert "FOLLOW-UP" in ca_block
    assert "removed" in ca_block.lower()
    # `assistant_reply` self-consistency contract is in the prompt body so
    # the model is told to use the same course list / total_units it produced.
    assert "self-consistent with `recommended`" in ca_block.lower()


def test_summarize_previous_plan_is_bounded_and_gracefully_empty():
    """Defensive helper checks: don't blow the prompt up, don't crash on None."""
    assert planning_agent._summarize_previous_plan(None) == ""
    assert planning_agent._summarize_previous_plan({}) == ""
    assert planning_agent._summarize_previous_plan({"recommended": []}) == ""

    big = {"recommended": [{"course": f"X {i}", "category": "C", "units": 4, "reason": "r"} for i in range(50)],
           "total_units": 200}
    out = planning_agent._summarize_previous_plan(big)
    # It caps at the first 8 items.
    assert out.count("\n- ") <= 8
    assert out.startswith("=== CURRENT STATE")
