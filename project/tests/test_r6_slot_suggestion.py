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
            "meeting_start_min": 9 * 60,
            "meeting_end_min": 9 * 60 + 50,
        },
        # MWF 14:00–14:50
        ("MATH", "53"): {
            "instructors": ["Carl Gauss"],
            "meeting_days": _MWF,
            "meeting_start_min": 14 * 60,
            "meeting_end_min": 14 * 60 + 50,
        },
        # TuTh 9:00–10:15
        ("ENGL", "1"): {
            "instructors": ["Jane Austen"],
            "meeting_days": _TUTH,
            "meeting_start_min": 9 * 60,
            "meeting_end_min": 10 * 60 + 15,
        },
    }


@pytest.fixture(autouse=True)
def _stub_loaders(monkeypatch):
    monkeypatch.setattr(planning_agent, "load_schedule_section_index", _fake_schedule)
    monkeypatch.setattr(planning_agent, "load_instructor_ratings", lambda: [])
    monkeypatch.setattr(
        planning_agent,
        "load_course_units_index",
        lambda: {("CSEN", "161"): 4, ("MATH", "53"): 4, ("ENGL", "1"): 4},
    )
    monkeypatch.setattr(planning_agent, "load_category_course_index", lambda: {})
    monkeypatch.setattr(planning_agent, "course_title_for", lambda key: f"{key[0]} {key[1]} title")


def test_suggest_courses_for_slot_returns_matches():
    """A slot with overlapping courses must return non-empty, well-formed candidates.

    Regression: the day filter previously compared a day *char* ("M") against
    the int day list ([0,2,4]) and never matched, so every slot returned [].
    """
    result = suggest_courses_for_slot(
        day_index=0,  # Monday
        start_min=9 * 60,  # 9:00 AM
        end_min=10 * 60,  # 10:00 AM
        missing_details=[{"course": "CSEN 161", "category": "Core", "units": 4}],
        exclude_codes=[],
    )

    assert isinstance(result, list)
    assert 0 < len(result) <= 5
    codes = [c["course"] for c in result]
    assert "CSEN 161" in codes  # MWF 9am overlaps the Monday 9–10am slot

    candidate = next(c for c in result if c["course"] == "CSEN 161")
    for field in ("course", "title", "units", "instructor", "rating", "difficulty", "rationale"):
        assert field in candidate


def test_suggest_courses_excludes_specified_codes():
    """Excluded codes must not appear in the results."""
    full = suggest_courses_for_slot(
        day_index=0, start_min=9 * 60, end_min=10 * 60, missing_details=[], exclude_codes=[]
    )
    assert full, "expected non-empty baseline"
    excluded = full[0]["course"]

    pruned = suggest_courses_for_slot(
        day_index=0,
        start_min=9 * 60,
        end_min=10 * 60,
        missing_details=[],
        exclude_codes=[excluded],
    )
    assert excluded not in [c["course"] for c in pruned]


def test_suggest_courses_respects_day_of_week():
    """Only courses meeting on the requested weekday are returned."""
    mon = [c["course"] for c in suggest_courses_for_slot(
        day_index=0, start_min=9 * 60, end_min=10 * 60, missing_details=[], exclude_codes=[]
    )]
    assert "CSEN 161" in mon  # MWF
    assert "ENGL 1" not in mon  # TuTh — wrong day

    tue = [c["course"] for c in suggest_courses_for_slot(
        day_index=1, start_min=9 * 60, end_min=10 * 60, missing_details=[], exclude_codes=[]
    )]
    assert "ENGL 1" in tue  # TuTh
    assert "CSEN 161" not in tue  # MWF — wrong day


def test_suggest_courses_respects_time_slot():
    """Only courses overlapping the requested time window are returned."""
    morning = [c["course"] for c in suggest_courses_for_slot(
        day_index=0, start_min=9 * 60, end_min=10 * 60, missing_details=[], exclude_codes=[]
    )]
    assert "CSEN 161" in morning  # 9:00–9:50 overlaps
    assert "MATH 53" not in morning  # 14:00 — no overlap

    afternoon = [c["course"] for c in suggest_courses_for_slot(
        day_index=0, start_min=14 * 60, end_min=15 * 60, missing_details=[], exclude_codes=[]
    )]
    assert "MATH 53" in afternoon  # 14:00–14:50 overlaps
    assert "CSEN 161" not in afternoon  # 9:00 — no overlap


def test_weekend_index_returns_empty():
    """day_index >= 5 (Sat/Sun) has no weekday courses."""
    assert suggest_courses_for_slot(
        day_index=5, start_min=9 * 60, end_min=10 * 60, missing_details=[], exclude_codes=[]
    ) == []
