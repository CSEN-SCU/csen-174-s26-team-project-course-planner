"""Slot popover no longer returns a separate enrichment block."""

from __future__ import annotations

import pytest

from agents import planning_agent
from agents.planning_agent import suggest_courses_for_slot

_MWF = [0, 2, 4]


def _fake_schedule() -> dict:
    return {
        ("CHIN", "125"): {
            "instructors": ["Prof A"],
            "meeting_days": _MWF,
            "meeting_start_min": 60,
            "meeting_end_min": 110,
        },
        ("ENGL", "1"): {
            "instructors": ["Prof B"],
            "meeting_days": _MWF,
            "meeting_start_min": 60,
            "meeting_end_min": 110,
        },
    }


@pytest.fixture(autouse=True)
def _stub_loaders(monkeypatch):
    monkeypatch.setattr(planning_agent, "load_schedule_section_index", _fake_schedule)
    monkeypatch.setattr(planning_agent, "load_instructor_ratings", lambda: {})
    monkeypatch.setattr(
        planning_agent,
        "load_course_units_index",
        lambda: {("CHIN", "125"): 5},
    )
    monkeypatch.setattr(planning_agent, "load_category_course_index", lambda: {})
    monkeypatch.setattr(
        planning_agent,
        "load_course_titles_index",
        lambda: {("CHIN", "125"): "Chinese Film"},
    )
    monkeypatch.setattr(
        planning_agent,
        "course_title_for",
        lambda course_code, _titles: f"{course_code} title",
    )


def test_slot_suggestion_omits_enrichment_block():
    out = suggest_courses_for_slot(
        day_index=0,
        start_min=60,
        end_min=120,
        missing_details=[{"requirement": "RTC 3"}],
        exclude_codes=["CHIN 1", "THTR 189"],
    )
    assert "enrichment" not in out
    assert out.get("candidates") == []


def test_slot_suggestion_does_not_add_chin_enrichment_when_gap_open():
    missing = [{"requirement": "Educational Enrichment – Courses"}]
    out = suggest_courses_for_slot(
        day_index=0,
        start_min=60,
        end_min=120,
        missing_details=missing,
        exclude_codes=[],
    )
    assert "enrichment" not in out
    codes = [c["course"] for c in out.get("candidates") or []]
    assert "CHIN 125" not in codes
