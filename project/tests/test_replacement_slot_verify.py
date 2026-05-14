"""Programmatic checks for calendar replacement vs Find Course Sections patterns."""

from __future__ import annotations

import pytest

from utils.replacement_slot_verify import (
    gap_category_for_course,
    new_recommended_courses,
    slot_matches_vacated_window,
    verify_calendar_replacements,
)


def test_slot_overlap_same_column():
    vac = {"days": ["M", "W"], "start": "10:00 AM", "end": "11:00 AM"}
    raw = "M W F | 10:15 AM - 10:50 AM"
    assert slot_matches_vacated_window(0, vac, raw) is True


def test_slot_no_overlap_times():
    vac = {"days": ["M"], "start": "10:00 AM", "end": "11:00 AM"}
    raw = "M | 2:00 PM - 3:00 PM"
    assert slot_matches_vacated_window(0, vac, raw) is False


def test_new_recommended_courses_diff():
    old = [{"course": "COEN 146", "units": 4}]
    new = [{"course": "COEN 146", "units": 4}, {"course": "COEN 174", "units": 4}]
    assert new_recommended_courses(old, new, "ELEN 153") == ["COEN 174"]


def test_gap_category_match():
    gaps = [{"course": "COEN 174", "category": "Core", "units": 4}]
    assert gap_category_for_course(gaps, "COEN 174") == "Core"


def test_verify_placeholder_when_no_new_codes():
    rows = verify_calendar_replacements(
        old_plan={"recommended": [{"course": "A", "units": 1}]},
        new_plan={"recommended": [{"course": "A", "units": 1}]},
        gaps=[],
        removed_course="B",
        vacated_col_i=0,
        vacated_parsed={"days": ["M"], "start": "9:00 AM", "end": "10:00 AM"},
        base_schedule_map={},
    )
    assert len(rows) == 1
    assert "no new course" in rows[0]["Notes"].lower()
