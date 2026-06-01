"""Multi-section offered catalog prompt block."""

from __future__ import annotations

from agents.planning_agent import build_offered_catalog_block


def test_catalog_lists_all_sections_for_multi_section_course():
    offered = [
        {
            "course": "CSEN 174",
            "title": "Software Engineering",
            "units": 4,
            "meeting_days": [0, 2, 4],
            "meeting_start_min": 150,
            "meeting_end_min": 225,
        },
    ]
    all_sections = {
        ("CSEN", "174"): [
            {
                "section": 1,
                "meeting_days": [0, 2, 4],
                "meeting_start_min": 150,
                "meeting_end_min": 225,
                "instructors": ["A"],
            },
            {
                "section": 2,
                "meeting_days": [0, 2, 4],
                "meeting_start_min": 300,
                "meeting_end_min": 375,
                "instructors": ["B"],
            },
        ],
    }
    block = build_offered_catalog_block(
        offered,
        {"CSEN 174"},
        all_sections=all_sections,
    )
    assert "• sec 1:" in block
    assert "• sec 2:" in block
    assert "10:30 AM" in block
    assert "1:00 PM" in block
