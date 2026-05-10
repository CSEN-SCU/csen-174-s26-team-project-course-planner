"""Calendar-driven plan follow-up strings."""

from __future__ import annotations

from utils.calendar_plan_followup import build_remove_and_replace_preference


def test_followup_names_course_and_forbids_recommendation():
    s = build_remove_and_replace_preference(
        ["COEN 146"],
        "Monday",
        {"days": ["M"], "start": "10:00 AM", "end": "11:15 AM"},
    )
    assert "COEN 146" in s
    assert "must NOT include" in s
    assert "Monday" in s
    assert "10:00 AM" in s
    assert "category" in s.lower() or "requirement" in s.lower()


def test_followup_time_tbd_branch():
    s = build_remove_and_replace_preference(["ELEN 153"], None, None)
    assert "ELEN 153" in s
    assert "Time TBD" in s or "unknown" in s.lower()
