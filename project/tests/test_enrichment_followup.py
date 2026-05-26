"""Deterministic enrichment follow-up must append CHIN without LLM."""

from __future__ import annotations

from utils.enrichment_resolver import (
    should_run_enrichment_followup,
    try_enrichment_followup_plan,
    user_mentions_enrichment,
)


def test_user_mentions_enrichment():
    assert user_mentions_enrichment("我想要一个中文 enrichment 课。")
    assert not user_mentions_enrichment("加一门数学课")


def test_should_run_without_missing_gap_if_user_asks():
    assert should_run_enrichment_followup(
        "中文 enrichment 课",
        [{"requirement": "Core: ENGR: RTC 3"}],
    )


def test_try_followup_appends_chin(monkeypatch):
    fake_sched = {
        ("CHIN", "125"): {
            "instructors": ["Prof"],
            "meeting_days": [0, 2, 4],
            "meeting_start_min": 300,
            "meeting_end_min": 365,
        },
        ("THTR", "189"): {
            "instructors": ["Brian"],
            "meeting_days": [1, 3],
            "meeting_start_min": 250,
            "meeting_end_min": 340,
        },
    }
    monkeypatch.setattr(
        "utils.scu_course_schedule_xlsx.load_schedule_section_index",
        lambda: fake_sched,
    )
    monkeypatch.setattr(
        "utils.scu_course_schedule_xlsx.load_course_titles_index",
        lambda: {("CHIN", "125"): "Chinese Film"},
    )
    monkeypatch.setattr(
        "utils.scu_course_schedule_xlsx.load_course_units_index",
        lambda: {("CHIN", "125"): 5},
    )
    monkeypatch.setattr("utils.scu_course_schedule_xlsx.load_instructor_ratings", lambda: {})

    prev = {
        "recommended": [
            {
                "course": "THTR 189",
                "units": 5,
                "title": "ELSJ",
                "category": "Core",
                "reason": "x",
            }
        ],
        "total_units": 5,
    }
    out = try_enrichment_followup_plan(
        user_preference="我想要一个中文 enrichment 课。",
        missing_details=[{"requirement": "Core: ENGR: ELSJ"}],
        previous_plan=prev,
    )
    assert out is not None
    codes = [r["course"] for r in out["recommended"]]
    assert "THTR 189" in codes
    assert "CHIN 125" in codes
    assert "CHIN 125" in out["assistant_reply"]
