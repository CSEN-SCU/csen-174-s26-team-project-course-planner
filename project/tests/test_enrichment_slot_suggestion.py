"""Slot popover returns a separate enrichment block for department tracks."""

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


def test_slot_enrichment_shows_when_chin_on_plan_without_gap():
    """Gap row may disappear after CHIN 1 is scheduled; popover still shows enrichment."""
    out = suggest_courses_for_slot(
        day_index=0,
        start_min=60,
        end_min=120,
        missing_details=[{"requirement": "RTC 3"}],
        exclude_codes=["CHIN 1", "THTR 189"],
        user_preference="我现在是中国人，所以我只能上高阶的中文课",
    )
    enrich = out.get("enrichment")
    assert enrich is not None
    assert enrich.get("track_label") == "中文 (CHIN)"
    codes = [c["course"] for c in enrich.get("candidates") or []]
    assert "CHIN 1" not in codes
    assert "CHIN 125" in codes


def test_slot_enrichment_block_lists_chin_at_slot():
    missing = [{"requirement": "Educational Enrichment – Courses"}]
    out = suggest_courses_for_slot(
        day_index=0,
        start_min=60,
        end_min=120,
        missing_details=missing,
        exclude_codes=[],
        user_preference="中文 enrichment",
    )
    enrich = out.get("enrichment")
    assert enrich is not None
    assert enrich.get("track_label") == "中文 (CHIN)"
    codes = [c["course"] for c in enrich.get("candidates") or []]
    assert "CHIN 125" in codes
    assert enrich["candidates"][0].get("kind") == "enrichment"
