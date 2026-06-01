"""Schedule preference parsing and section ranking."""

from __future__ import annotations

from utils.schedule_preferences import (
    clock_to_calendar_offset,
    parse_slot_avoidances,
    pick_best_section_dict,
    preference_score_for_section,
    section_matches_avoidance,
    SlotAvoidance,
)


def test_clock_to_calendar_offset():
    assert clock_to_calendar_offset(10, 30, "am") == 150
    assert clock_to_calendar_offset(1, 0, "pm") == 300


def test_parse_mwf_at_1030_avoidance():
    av = parse_slot_avoidances("I do not want a MWF class at 10:30")
    assert len(av) >= 1
    assert av[0].days == frozenset({0, 2, 4})
    assert av[0].start_min <= 150 <= av[0].end_min


def test_section_matches_avoidance_on_mwf_1030():
    av = SlotAvoidance(days=frozenset({0, 2, 4}), start_min=130, end_min=170)
    sec = {
        "section": 1,
        "meeting_days": [0, 2, 4],
        "meeting_start_min": 150,
        "meeting_end_min": 225,
    }
    assert section_matches_avoidance(sec, av)
    sec2 = {
        "section": 2,
        "meeting_days": [0, 2, 4],
        "meeting_start_min": 300,
        "meeting_end_min": 375,
    }
    assert not section_matches_avoidance(sec2, av)


def test_pick_best_section_prefers_non_avoided_time():
    sections = [
        {
            "section": 1,
            "meeting_days": [0, 2, 4],
            "meeting_start_min": 150,
            "meeting_end_min": 225,
            "instructor_rating": 4.8,
        },
        {
            "section": 2,
            "meeting_days": [0, 2, 4],
            "meeting_start_min": 300,
            "meeting_end_min": 375,
            "instructor_rating": 4.0,
        },
    ]
    chosen = pick_best_section_dict(sections, "no MWF class at 10:30")
    assert chosen["section"] == 2


def test_preference_score_penalizes_avoided_slot():
    bad = {"meeting_days": [0, 2, 4], "meeting_start_min": 150}
    good = {"meeting_days": [0, 2, 4], "meeting_start_min": 300}
    pref = "avoid MWF at 10:30"
    assert preference_score_for_section(good, pref) > preference_score_for_section(bad, pref)
