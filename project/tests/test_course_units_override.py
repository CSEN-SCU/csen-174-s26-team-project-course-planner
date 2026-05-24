"""Units must come from the schedule xlsx, not the LLM's guesses.

The LLM invents unit counts (CSEN 122 as 3u, its lab as 2u). The catalog
truth is CSEN 122 = 4u, CSEN 122L = 1u. These tests pin the
load_course_units_index loader, the course_units_for lookup, and the
end-to-end override in run_planning_agent.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from agents import planning_agent
from utils import scu_course_schedule_xlsx as sx
from support import schedule_xlsx_available


def _require_units_index():
    if not schedule_xlsx_available():
        pytest.skip("SCU_Find_Course_Sections.xlsx not available")
    idx = sx.load_course_units_index()
    if not idx:
        pytest.skip("SCU_Find_Course_Sections.xlsx not available")
    return idx


# ── loader + lookup ──────────────────────────────────────────────────────────


def test_units_index_loads_from_real_xlsx():
    idx = _require_units_index()
    assert sx.course_units_for("CSEN 122", idx) == 4
    assert sx.course_units_for("CSEN 122L", idx) == 1


def test_units_csen_coen_alias():
    idx = _require_units_index()
    # CSEN/COEN are mirrored; both resolve to the same units.
    assert sx.course_units_for("COEN 122", idx) == sx.course_units_for("CSEN 122", idx)


def test_units_for_unknown_returns_none():
    idx = _require_units_index()
    assert sx.course_units_for("ZZZZ 9000", idx) is None


def test_units_for_empty_index_returns_none():
    assert sx.course_units_for("CSEN 122", {}) is None


# ── end-to-end override in run_planning_agent ────────────────────────────────


def _stub_client(reply: dict):
    class _Models:
        def generate_content(self, model, contents, config):
            return SimpleNamespace(text=json.dumps(reply))

    return SimpleNamespace(models=_Models())


def _fake_schedule(*codes: str) -> dict:
    idx = {}
    for code in codes:
        subj, num = code.split()
        idx[(subj, num)] = {
            "instructors": [], "meeting_days": [],
            "meeting_start_min": None, "meeting_end_min": None,
        }
    return idx


def test_run_planning_agent_overrides_hallucinated_units(monkeypatch):
    # LLM returns WRONG units: lecture 3, lab 2.
    reply = {
        "recommended": [
            {"course": "CSEN 122", "title": "x", "category": "Major", "units": 3, "reason": "core"},
            {"course": "CSEN 122L", "title": "x", "category": "Major", "units": 2, "reason": "lab"},
        ],
        "total_units": 5,
        "advice": "ok",
        "assistant_reply": "done.",
    }
    monkeypatch.setattr(planning_agent, "get_genai_client", lambda **_: _stub_client(reply))
    monkeypatch.setattr(
        planning_agent, "load_schedule_section_index",
        lambda: _fake_schedule("CSEN 122", "CSEN 122L", "COEN 122", "COEN 122L"),
    )
    monkeypatch.setattr(planning_agent, "load_category_course_index", lambda: {})
    monkeypatch.setattr(planning_agent, "load_course_titles_index", lambda: {})
    # Real units: lecture 4, lab 1.
    monkeypatch.setattr(
        planning_agent, "load_course_units_index",
        lambda: {("CSEN", "122"): 4, ("CSEN", "122L"): 1,
                 ("COEN", "122"): 4, ("COEN", "122L"): 1},
    )

    out = planning_agent.run_planning_agent(
        missing_details=[
            {"course": "CSEN 122", "category": "Major", "units": 4},
            {"course": "CSEN 122L", "category": "Major", "units": 1},
        ],
        user_preference="architecture",
    )

    by_code = {r["course"]: r for r in out["recommended"]}
    assert by_code["CSEN 122"]["units"] == 4, "lecture units must be overridden to catalog 4"
    assert by_code["CSEN 122L"]["units"] == 1, "lab units must be overridden to catalog 1"
    # total recomputed from the corrected units.
    assert out["total_units"] == 5  # 4 + 1, not the LLM's 3 + 2


def test_units_kept_when_schedule_has_no_entry(monkeypatch):
    """If the catalog has no units for a course, keep the LLM's value."""
    reply = {
        "recommended": [{"course": "PHIL 11", "title": "Ethics", "category": "Core", "units": 4, "reason": "core"}],
        "total_units": 4,
        "advice": "ok",
        "assistant_reply": "done.",
    }
    monkeypatch.setattr(planning_agent, "get_genai_client", lambda **_: _stub_client(reply))
    monkeypatch.setattr(planning_agent, "load_schedule_section_index", lambda: _fake_schedule("PHIL 11"))
    monkeypatch.setattr(planning_agent, "load_category_course_index", lambda: {})
    monkeypatch.setattr(planning_agent, "load_course_titles_index", lambda: {})
    monkeypatch.setattr(planning_agent, "load_course_units_index", lambda: {})  # no units data

    out = planning_agent.run_planning_agent(
        missing_details=[{"course": "PHIL 11", "category": "Core", "units": 4}],
        user_preference="any",
    )
    assert out["recommended"][0]["units"] == 4
