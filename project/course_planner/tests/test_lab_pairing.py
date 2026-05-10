"""SCU lecture+lab co-requirements must be co-recommended.

Domain rule (CSEN/COEN/PHYS/CHEM/ELEN/BIOL): a course and its
trailing-L lab section are taken in the same quarter (e.g. CSEN 194 and
CSEN 194L). The planning agent must NEVER split a pair across quarters
when both halves are still in the student's gap.

These tests pin the post-processing safety net in
``agents.planning_agent`` so the rule survives even when the LLM forgets
or hallucinates only one half.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from agents import planning_agent


def _stub_client(reply: dict):
    class _Models:
        def generate_content(self, model, contents, config):  # noqa: D401
            return SimpleNamespace(text=json.dumps(reply))

    class _Client:
        models = _Models()

    return _Client()


# ---------------------------------------------------------------------------
# Pure helper unit tests (no mocked Gemini needed)
# ---------------------------------------------------------------------------


def test_pair_pulls_in_lab_when_only_lecture_recommended():
    recommended = [
        {"course": "CSEN 194", "category": "Senior Design", "units": 4, "reason": "kickoff"},
    ]
    missing_details = [
        {"course": "CSEN 194", "category": "Senior Design", "units": 4},
        {"course": "CSEN 194L", "category": "Senior Design", "units": 1},
    ]

    paired = planning_agent._pair_lab_corequirements(recommended, missing_details)

    codes = {item["course"] for item in paired}
    assert codes == {"CSEN 194", "CSEN 194L"}
    lab = next(i for i in paired if i["course"] == "CSEN 194L")
    assert lab["units"] == 1
    assert "co-requirement" in lab["reason"].lower()


def test_pair_pulls_in_lecture_when_only_lab_recommended():
    recommended = [
        {"course": "CSEN 194L", "category": "Senior Design", "units": 1, "reason": "lab"},
    ]
    missing_details = [
        {"course": "CSEN 194", "category": "Senior Design", "units": 4},
        {"course": "CSEN 194L", "category": "Senior Design", "units": 1},
    ]

    paired = planning_agent._pair_lab_corequirements(recommended, missing_details)

    codes = [item["course"] for item in paired]
    assert "CSEN 194" in codes
    assert "CSEN 194L" in codes


def test_pair_no_op_when_partner_not_in_gap():
    """If the lab is already satisfied (not in missing_details), do not invent it."""
    recommended = [
        {"course": "CSEN 194", "category": "Senior Design", "units": 4, "reason": "kickoff"},
    ]
    missing_details = [
        {"course": "CSEN 194", "category": "Senior Design", "units": 4},
        # CSEN 194L intentionally omitted.
    ]

    paired = planning_agent._pair_lab_corequirements(recommended, missing_details)

    assert [item["course"] for item in paired] == ["CSEN 194"]


def test_pair_skips_subjects_without_labs():
    """MATH 11 has no MATH 11L; never auto-add a fake lab partner."""
    recommended = [
        {"course": "MATH 11", "category": "Math Core", "units": 4, "reason": "calc"},
        {"course": "PHIL 11", "category": "Core", "units": 4, "reason": "core"},
    ]
    missing_details = [
        {"course": "MATH 11", "category": "Math Core", "units": 4},
        {"course": "PHIL 11", "category": "Core", "units": 4},
        # Even if a stray "MATH 11L" snuck into the gap, MATH is not in the
        # pairing whitelist so we must not auto-pair.
        {"course": "MATH 11L", "category": "Math Core", "units": 1},
    ]

    paired = planning_agent._pair_lab_corequirements(recommended, missing_details)

    codes = [item["course"] for item in paired]
    assert codes == ["MATH 11", "PHIL 11"]


def test_pair_idempotent_when_pair_already_present():
    recommended = [
        {"course": "CSEN 194", "category": "Senior Design", "units": 4, "reason": "kickoff"},
        {"course": "CSEN 194L", "category": "Senior Design", "units": 1, "reason": "lab"},
    ]
    missing_details = [
        {"course": "CSEN 194", "category": "Senior Design", "units": 4},
        {"course": "CSEN 194L", "category": "Senior Design", "units": 1},
    ]

    paired = planning_agent._pair_lab_corequirements(recommended, missing_details)

    assert len(paired) == 2
    assert paired == recommended


# ---------------------------------------------------------------------------
# End-to-end through run_planning_agent (with stubbed Gemini)
# ---------------------------------------------------------------------------


def test_run_planning_agent_auto_pairs_and_recomputes_total(monkeypatch):
    """The model returns lecture-only; the agent fills in the lab + new total."""
    reply = {
        "recommended": [
            {"course": "CSEN 194", "category": "Senior Design", "units": 4, "reason": "kickoff"},
            {"course": "PHIL 11", "category": "Core", "units": 4, "reason": "core"},
        ],
        "total_units": 8,
        "advice": "ok",
        "assistant_reply": "Here is a balanced first cut.",
    }
    monkeypatch.setattr(planning_agent, "get_genai_client", lambda **_kw: _stub_client(reply))

    out = planning_agent.run_planning_agent(
        missing_details=[
            {"course": "CSEN 194", "category": "Senior Design", "units": 4},
            {"course": "CSEN 194L", "category": "Senior Design", "units": 1},
            {"course": "PHIL 11", "category": "Core", "units": 4},
        ],
        user_preference="balanced quarter",
    )

    codes = [item["course"] for item in out["recommended"]]
    assert "CSEN 194" in codes
    assert "CSEN 194L" in codes, (
        "Lab co-requirement of CSEN 194 must be auto-paired when present in gap"
    )
    assert "PHIL 11" in codes
    assert out["total_units"] == 9, (
        "total_units must be recomputed (4 + 1 + 4 = 9) after pairing"
    )


def test_run_planning_agent_does_not_pair_when_lab_not_in_gap(monkeypatch):
    """If the student already finished CSEN 194L, leave the lecture alone."""
    reply = {
        "recommended": [
            {"course": "CSEN 194", "category": "Senior Design", "units": 4, "reason": "kickoff"},
        ],
        "total_units": 4,
        "advice": "ok",
        "assistant_reply": "Senior Design start.",
    }
    monkeypatch.setattr(planning_agent, "get_genai_client", lambda **_kw: _stub_client(reply))

    out = planning_agent.run_planning_agent(
        missing_details=[
            {"course": "CSEN 194", "category": "Senior Design", "units": 4},
            # CSEN 194L not in gap (already completed)
        ],
        user_preference="just senior design",
    )

    codes = [item["course"] for item in out["recommended"]]
    assert codes == ["CSEN 194"]
    assert out["total_units"] == 4


def test_run_planning_agent_pairs_phys_lecture_with_phys_lab(monkeypatch):
    """Pairing rule covers PHYS / CHEM / ELEN / BIOL too, not just CSEN."""
    reply = {
        "recommended": [
            {"course": "PHYS 31", "category": "Science Core", "units": 4, "reason": "mechanics"},
        ],
        "total_units": 4,
        "advice": "ok",
        "assistant_reply": "Solid science quarter.",
    }
    monkeypatch.setattr(planning_agent, "get_genai_client", lambda **_kw: _stub_client(reply))

    out = planning_agent.run_planning_agent(
        missing_details=[
            {"course": "PHYS 31", "category": "Science Core", "units": 4},
            {"course": "PHYS 31L", "category": "Science Core", "units": 1},
        ],
        user_preference="science focus",
    )

    codes = {item["course"] for item in out["recommended"]}
    assert codes == {"PHYS 31", "PHYS 31L"}
    assert out["total_units"] == 5
