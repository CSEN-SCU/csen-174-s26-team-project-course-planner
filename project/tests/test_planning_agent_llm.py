"""Tests for the LLM-driven planner (engine: ``llm_select``).

The model makes the course selection; Python enforces the hard SCU rules
afterward. These tests stub the Gemini client + xlsx loaders so the engine
runs without disk or network, and verify that:

  - the chosen courses + reasons flow through to ``recommended``;
  - codes the model invents (not offered next term) are dropped and reported
    in ``meta.validation.rejected``;
  - titles/units are always taken from the schedule xlsx, never the LLM;
  - already-completed courses are removed;
  - a named unit cap is enforced deterministically;
  - ``meta.validation.engine`` is ``"llm_select"``.
"""

from __future__ import annotations

import json

import pytest

from agents import planning_agent_llm as llm


class _FakeClient:
    """Mock the GenAI client; returns a caller-supplied JSON payload."""

    def __init__(self, payload: dict):
        self._text = json.dumps(payload)

        class _Models:
            def __init__(self, text):
                self._text = text

            def generate_content(self, *, model, contents, config):
                class _R:
                    pass

                r = _R()
                r.text = self._text
                return r

        self.models = _Models(self._text)


def _patch(monkeypatch, *, payload, offered=None):
    """Stub the LLM client + all xlsx loaders the engine touches."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(llm, "get_genai_client", lambda *, purpose: _FakeClient(payload))

    schedule_index = {
        ("CSEN", "174"): {"instructors": ["Smith"], "meeting_days": [0, 2]},
        ("MATH", "53"): {"instructors": ["Doe"], "meeting_days": [1, 3]},
        ("CSEN", "20"): {"instructors": ["Lee"], "meeting_days": [0]},
        ("CSEN", "20L"): {"instructors": ["Lee"], "meeting_days": [2]},
    }
    titles = {
        ("CSEN", "174"): "Software Engineering",
        ("MATH", "53"): "Linear Algebra",
        ("CSEN", "20"): "Object-Oriented Programming",
        ("CSEN", "20L"): "OOP Lab",
    }
    units = {
        ("CSEN", "174"): 4,
        ("MATH", "53"): 4,
        ("CSEN", "20"): 4,
        ("CSEN", "20L"): 1,
    }
    if offered is None:
        offered = [
            {"course": "CSEN 174", "title": "Software Engineering", "units": 4},
            {"course": "MATH 53", "title": "Linear Algebra", "units": 4},
            {"course": "CSEN 20", "title": "Object-Oriented Programming", "units": 4},
            {"course": "CSEN 20L", "title": "OOP Lab", "units": 1},
        ]

    monkeypatch.setattr(llm, "load_schedule_section_index", lambda: schedule_index)
    monkeypatch.setattr(llm, "load_category_course_index", lambda: {})
    monkeypatch.setattr(llm, "load_course_titles_index", lambda: titles)
    monkeypatch.setattr(llm, "load_course_units_index", lambda: units)
    monkeypatch.setattr(llm, "list_offered_courses", lambda: offered)
    monkeypatch.setattr(llm, "load_all_course_sections", lambda: {})

    # Keep the major-bulletin block hermetic (no disk read of data/majors).
    import utils.major_requirements as mr

    monkeypatch.setattr(
        mr, "build_major_advisor_block", lambda **kw: ("", "csen")
    )


def _rec(course, title="WRONG", units=99, reason="because"):
    return {"course": course, "title": title, "category": "Major", "units": units, "reason": reason}


def test_engine_label_and_basic_selection(monkeypatch):
    _patch(
        monkeypatch,
        payload={
            "recommended": [_rec("CSEN 174", title="x", units=4)],
            "total_units": 4,
            "advice": "Good plan.",
            "assistant_reply": "I picked CSEN 174 (4 units).",
        },
    )
    out = llm.run_llm_planner(
        [{"course": "CSEN 174", "category": "Major"}], "plan my next quarter"
    )
    assert out["meta"]["validation"]["engine"] == "llm_select"
    codes = [r["course"] for r in out["recommended"]]
    assert "CSEN 174" in codes


def test_hallucinated_codes_are_dropped_and_reported(monkeypatch):
    _patch(
        monkeypatch,
        payload={
            "recommended": [
                _rec("CSEN 174", units=4),
                _rec("FAKE 999", units=4),  # not offered → must be dropped
            ],
            "total_units": 8,
            "advice": "a",
            "assistant_reply": "b",
        },
    )
    out = llm.run_llm_planner(
        [{"course": "CSEN 174", "category": "Major"}], "give me a plan"
    )
    codes = [r["course"] for r in out["recommended"]]
    assert "CSEN 174" in codes
    assert "FAKE 999" not in codes
    assert "FAKE 999" in out["meta"]["validation"]["rejected"]


def test_titles_and_units_come_from_xlsx_not_llm(monkeypatch):
    _patch(
        monkeypatch,
        payload={
            "recommended": [_rec("CSEN 174", title="Totally Wrong Title", units=99)],
            "total_units": 99,
            "advice": "a",
            "assistant_reply": "b",
        },
    )
    out = llm.run_llm_planner(
        [{"course": "CSEN 174", "category": "Major"}], "plan"
    )
    rec = next(r for r in out["recommended"] if r["course"] == "CSEN 174")
    assert rec["title"] == "Software Engineering"
    assert rec["units"] == 4
    assert out["total_units"] == 4


def test_completed_courses_are_removed(monkeypatch):
    _patch(
        monkeypatch,
        payload={
            "recommended": [_rec("CSEN 174", units=4), _rec("MATH 53", units=4)],
            "total_units": 8,
            "advice": "a",
            "assistant_reply": "b",
        },
    )
    out = llm.run_llm_planner(
        [{"course": "CSEN 174", "category": "Major"}, {"course": "MATH 53", "category": "Major"}],
        "plan",
        completed_course_codes=["CSEN 174"],
    )
    codes = [r["course"] for r in out["recommended"]]
    assert "CSEN 174" not in codes
    assert "MATH 53" in codes
    assert "CSEN 174" in out["meta"]["validation"]["removed_completed"]


def test_unit_cap_is_enforced(monkeypatch):
    _patch(
        monkeypatch,
        payload={
            "recommended": [_rec("CSEN 174", units=4), _rec("MATH 53", units=4)],
            "total_units": 8,
            "advice": "a",
            "assistant_reply": "b",
        },
    )
    out = llm.run_llm_planner(
        [{"course": "CSEN 174", "category": "Major"}, {"course": "MATH 53", "category": "Major"}],
        "max 4 units please",
    )
    assert out["total_units"] <= 4


def test_lab_partner_is_paired(monkeypatch):
    _patch(
        monkeypatch,
        payload={
            "recommended": [_rec("CSEN 20", units=4)],
            "total_units": 4,
            "advice": "a",
            "assistant_reply": "b",
        },
    )
    out = llm.run_llm_planner(
        [
            {"course": "CSEN 20", "category": "Major"},
            {"course": "CSEN 20L", "category": "Major"},
        ],
        "plan",
    )
    codes = [r["course"] for r in out["recommended"]]
    assert "CSEN 20" in codes
    assert "CSEN 20L" in codes


def test_raises_without_any_data(monkeypatch):
    _patch(monkeypatch, payload={"recommended": [], "total_units": 0, "advice": "", "assistant_reply": ""})
    with pytest.raises(ValueError):
        llm.run_llm_planner([], "")


def test_llm_stamps_section_matching_schedule_preference(monkeypatch):
    all_secs = {
        ("CSEN", "174"): [
            {
                "section": 1,
                "meeting_days": [0, 2, 4],
                "meeting_start_min": 150,
                "meeting_end_min": 225,
                "instructors": ["Early"],
            },
            {
                "section": 2,
                "meeting_days": [0, 2, 4],
                "meeting_start_min": 300,
                "meeting_end_min": 375,
                "instructors": ["Late"],
            },
        ],
    }
    _patch(
        monkeypatch,
        payload={
            "recommended": [_rec("CSEN 174", units=4)],
            "total_units": 4,
            "advice": "a",
            "assistant_reply": "b",
        },
    )
    monkeypatch.setattr(llm, "load_all_course_sections", lambda: all_secs)

    out = llm.run_llm_planner(
        [{"course": "CSEN 174", "category": "Major"}],
        "I do not want a MWF class at 10:30",
    )
    row = out["recommended"][0]
    assert row["_chosen_section"] == 2
    assert row["meeting_start_min"] == 300


def test_unit_floor_tops_up_below_minimum_plan(monkeypatch):
    """The engine returns an 8-unit plan; the floor must bump it to >= 12.

    This is the bug the user kept hitting: the LLM returns a thin plan and the
    floor top-up (added in this engine, not just the legacy one) must fire.
    """
    _patch(
        monkeypatch,
        payload={
            "recommended": [_rec("CSEN 174", units=4)],  # 4 units only
            "total_units": 4,
            "advice": "a",
            "assistant_reply": "b",
        },
    )
    out = llm.run_llm_planner(
        [
            {"course": "CSEN 174", "category": "Major"},
            {"course": "MATH 53", "category": "Major"},
            {"course": "CSEN 20", "category": "Major"},
        ],
        "give me a plan",
    )
    assert out["total_units"] >= 12
    assert out["meta"]["validation"]["added_for_unit_floor"]


def test_unit_floor_skipped_for_part_time_student(monkeypatch):
    """Part-time students intentionally sit below the full-time minimum."""
    _patch(
        monkeypatch,
        payload={
            "recommended": [_rec("CSEN 174", units=4)],
            "total_units": 4,
            "advice": "a",
            "assistant_reply": "b",
        },
    )
    out = llm.run_llm_planner(
        [
            {"course": "CSEN 174", "category": "Major"},
            {"course": "MATH 53", "category": "Major"},
            {"course": "CSEN 20", "category": "Major"},
        ],
        "I'm a part-time student, keep it light",
    )
    assert out["total_units"] == 4
    assert out["meta"]["validation"]["added_for_unit_floor"] == []


def test_unit_floor_respects_named_cap(monkeypatch):
    """The floor never pushes the plan above a student-stated cap."""
    _patch(
        monkeypatch,
        payload={
            "recommended": [_rec("CSEN 174", units=4)],
            "total_units": 4,
            "advice": "a",
            "assistant_reply": "b",
        },
    )
    out = llm.run_llm_planner(
        [
            {"course": "CSEN 174", "category": "Major"},
            {"course": "MATH 53", "category": "Major"},
        ],
        "max 5 units please",
    )
    # 4 + 4 would exceed 5, so no fill is possible under the cap.
    assert out["total_units"] <= 5


def test_advice_phantom_course_is_scrubbed(monkeypatch):
    """A course narrated in `advice` but absent from the plan is rewritten out."""
    _patch(
        monkeypatch,
        payload={
            "recommended": [_rec("CSEN 174", units=4)],
            "total_units": 4,
            "advice": "I recommend taking GREK 101 to round out your schedule.",
            "assistant_reply": "b",
        },
    )
    out = llm.run_llm_planner(
        [{"course": "CSEN 174", "category": "Major"}],
        "I'm a part-time student",  # part-time → no floor fill muddies the check
    )
    assert "GREK 101" not in out["advice"]


def test_advice_deferral_guidance_is_preserved(monkeypatch):
    """'Not offered / take it later' guidance about an off-plan course stays."""
    advice = "Note: CSEN 195 is not offered next quarter; plan to take it later."
    _patch(
        monkeypatch,
        payload={
            "recommended": [_rec("CSEN 174", units=4)],
            "total_units": 4,
            "advice": advice,
            "assistant_reply": "b",
        },
    )
    out = llm.run_llm_planner(
        [{"course": "CSEN 174", "category": "Major"}],
        "I'm a part-time student",
    )
    assert out["advice"] == advice


def test_prompt_includes_full_offered_catalog_with_schedule(monkeypatch):
    captured: list[str] = []

    def fake_call(prompt, system_instruction, model):
        captured.append(prompt)
        return (
            {
                "recommended": [_rec("CSEN 174", units=4)],
                "total_units": 4,
                "advice": "a",
                "assistant_reply": "b",
            },
            model,
        )

    _patch(
        monkeypatch,
        payload={"recommended": [], "total_units": 0, "advice": "", "assistant_reply": ""},
        offered=[
            {
                "course": "CSEN 174",
                "title": "Software Engineering",
                "units": 4,
                "meeting_days": [0, 2],
                "meeting_start_min": 60,
                "meeting_end_min": 165,
            },
            {
                "course": "MATH 53",
                "title": "Linear Algebra",
                "units": 4,
                "meeting_days": [1, 3],
                "meeting_start_min": 120,
                "meeting_end_min": 225,
            },
        ],
    )
    monkeypatch.setattr(llm, "_call_selection_llm", fake_call)

    llm.run_llm_planner(
        [{"course": "CSEN 174", "category": "Major"}], "minimize classes on Tuesdays"
    )

    assert captured, "expected LLM prompt to be captured"
    prompt = captured[0]
    assert "=== COURSES CONFIRMED IN NEXT-TERM SCHEDULE ===" not in prompt
    assert "=== FULL LIST OF COURSES OFFERED NEXT QUARTER ===" in prompt
    assert "CSEN 174 — Software Engineering (4u; M W 9:00 AM–10:45 AM) ★" in prompt
    assert "MATH 53 — Linear Algebra (4u; T Th 10:00 AM–11:45 AM)" in prompt
