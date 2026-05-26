"""Test R6 slot-based course suggestion functionality.

These tests stub the schedule/ratings/units/category loaders so they do not
depend on the (gitignored) ``SCU_Find_Course_Sections.xlsx`` and stay
deterministic. Crucially, ``meeting_days`` is a list of weekday *ints*
(0=Mon..4=Fri) — matching what ``load_schedule_section_index`` actually
produces — so the day-overlap filter is exercised against real-shaped data.
"""

from __future__ import annotations

import pytest

from agents import planning_agent
from agents.planning_agent import suggest_courses_for_slot

# Weekday ints: 0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri
_MWF = [0, 2, 4]
_TUTH = [1, 3]


def _fake_schedule() -> dict:
    return {
        # MWF 9:00–9:50
        ("CSEN", "161"): {
            "instructors": ["Ada Lovelace"],
            "meeting_days": _MWF,
            # minutes-from-calendar-start (8:00 AM)
            "meeting_start_min": 1 * 60,  # 9:00
            "meeting_end_min": 1 * 60 + 50,  # 9:50
        },
        # MWF 14:00–14:50
        ("MATH", "53"): {
            "instructors": ["Carl Gauss"],
            "meeting_days": _MWF,
            "meeting_start_min": 6 * 60,  # 14:00
            "meeting_end_min": 6 * 60 + 50,  # 14:50
        },
        # TuTh 9:00–10:15
        ("ENGL", "1"): {
            "instructors": ["Jane Austen"],
            "meeting_days": _TUTH,
            "meeting_start_min": 1 * 60,  # 9:00
            "meeting_end_min": 2 * 60 + 15,  # 10:15
        },
    }


@pytest.fixture(autouse=True)
def _stub_loaders(monkeypatch):
    monkeypatch.setattr(planning_agent, "load_schedule_section_index", _fake_schedule)
    monkeypatch.setattr(planning_agent, "load_instructor_ratings", lambda: {})
    monkeypatch.setattr(
        planning_agent,
        "load_course_units_index",
        lambda: {("CSEN", "161"): 4, ("MATH", "53"): 4, ("ENGL", "1"): 4},
    )
    monkeypatch.setattr(planning_agent, "load_category_course_index", lambda: {})
    monkeypatch.setattr(planning_agent, "load_course_titles_index", lambda: {})
    monkeypatch.setattr(
        planning_agent,
        "course_title_for",
        lambda course_code, _titles_index: f"{course_code} title",
    )


def _md(*courses: str) -> list[dict]:
    return [{"course": c, "requirement": c, "status": "Not Satisfied"} for c in courses]


def test_suggest_courses_for_slot_returns_matches():
    """A slot with overlapping courses must return non-empty, well-formed candidates."""
    result = suggest_courses_for_slot(
        day_index=0,  # Monday
        start_min=1 * 60,
        end_min=2 * 60,
        missing_details=_md("CSEN 161"),
        exclude_codes=[],
    )

    candidates = result["candidates"]
    assert isinstance(candidates, list)
    assert 0 < len(candidates) <= 5
    assert result["message"] is None
    codes = [c["course"] for c in candidates]
    assert "CSEN 161" in codes

    candidate = next(c for c in candidates if c["course"] == "CSEN 161")
    assert candidate.get("covers")
    for field in ("course", "title", "units", "instructor", "rating", "difficulty", "rationale"):
        assert field in candidate
    assert candidate["meeting_days"] == _MWF
    assert candidate["meeting_start_min"] == 1 * 60
    assert candidate["meeting_end_min"] == 1 * 60 + 50


def test_suggest_does_not_return_time_only_fillers():
    """Courses that only fit the slot but not a requirement must not appear."""
    result = suggest_courses_for_slot(
        day_index=0,
        start_min=6 * 60,  # afternoon — MATH 53 meets here, CSEN 161 is morning only
        end_min=7 * 60,
        missing_details=_md("MATH 53"),
        exclude_codes=[],
    )
    codes = [c["course"] for c in result["candidates"]]
    assert "MATH 53" in codes
    assert "CSEN 161" not in codes


def test_suggest_empty_slot_returns_message():
    """No gap-filling course at this time → empty list + guidance message."""
    result = suggest_courses_for_slot(
        day_index=0,
        start_min=6 * 60,
        end_min=7 * 60,
        missing_details=_md("CSEN 161"),  # CSEN is 9am, not afternoon
        exclude_codes=[],
    )
    assert result["candidates"] == []
    assert isinstance(result["message"], str)
    assert result["message"]


def test_suggest_courses_excludes_specified_codes():
    """Excluded codes must not appear in the results."""
    full = suggest_courses_for_slot(
        day_index=0,
        start_min=1 * 60,
        end_min=2 * 60,
        missing_details=_md("CSEN 161", "MATH 53"),
        exclude_codes=[],
    )
    assert full["candidates"]
    excluded = full["candidates"][0]["course"]

    pruned = suggest_courses_for_slot(
        day_index=0,
        start_min=1 * 60,
        end_min=2 * 60,
        missing_details=_md("CSEN 161", "MATH 53"),
        exclude_codes=[excluded],
    )
    assert excluded not in [c["course"] for c in pruned["candidates"]]


def test_suggest_courses_respects_day_of_week():
    """Only courses meeting on the requested weekday are returned."""
    md = _md("CSEN 161", "ENGL 1")
    mon = [c["course"] for c in suggest_courses_for_slot(
        day_index=0, start_min=1 * 60, end_min=2 * 60, missing_details=md, exclude_codes=[],
    )["candidates"]]
    assert "CSEN 161" in mon
    assert "ENGL 1" not in mon

    tue = [c["course"] for c in suggest_courses_for_slot(
        day_index=1, start_min=1 * 60, end_min=2 * 60, missing_details=md, exclude_codes=[],
    )["candidates"]]
    assert "ENGL 1" in tue
    assert "CSEN 161" not in tue


def test_suggest_courses_respects_time_slot():
    """Only courses overlapping the requested time window are returned."""
    md = _md("CSEN 161", "MATH 53")
    morning = [c["course"] for c in suggest_courses_for_slot(
        day_index=0, start_min=1 * 60, end_min=2 * 60, missing_details=md, exclude_codes=[],
    )["candidates"]]
    assert "CSEN 161" in morning
    assert "MATH 53" not in morning

    afternoon = [c["course"] for c in suggest_courses_for_slot(
        day_index=0, start_min=6 * 60, end_min=7 * 60, missing_details=md, exclude_codes=[],
    )["candidates"]]
    assert "MATH 53" in afternoon
    assert "CSEN 161" not in afternoon


def test_weekend_index_returns_empty():
    """day_index >= 5 (Sat/Sun) has no weekday courses."""
    result = suggest_courses_for_slot(
        day_index=5,
        start_min=1 * 60,
        end_min=2 * 60,
        missing_details=_md("CSEN 161"),
        exclude_codes=[],
    )
    assert result["candidates"] == []
    assert result["message"]
