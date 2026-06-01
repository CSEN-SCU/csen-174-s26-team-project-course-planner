"""Deterministic enrichment follow-up appends department-track courses without LLM."""

from __future__ import annotations

from utils.enrichment_resolver import (
    should_run_enrichment_followup,
    try_enrichment_followup_plan,
    user_mentions_enrichment,
)


def test_user_mentions_enrichment():
    assert user_mentions_enrichment("I want an HIST enrichment course.")
    assert not user_mentions_enrichment("add a math course")


def test_should_run_without_missing_gap_if_user_asks():
    assert should_run_enrichment_followup(
        "HIST enrichment course",
        [{"requirement": "Core: ENGR: RTC 3"}],
    )


def test_try_followup_appends_hist(monkeypatch):
    fake_sched = {
        ("HIST", "50"): {
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
        lambda: {("HIST", "50"): "Modern History"},
    )
    monkeypatch.setattr(
        "utils.scu_course_schedule_xlsx.load_course_units_index",
        lambda: {("HIST", "50"): 5},
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
        user_preference="Add an HIST enrichment course.",
        missing_details=[{"requirement": "Core: ENGR: ELSJ"}],
        previous_plan=prev,
    )
    assert out is not None
    codes = [r["course"] for r in out["recommended"]]
    assert "THTR 189" in codes
    assert "HIST 50" in codes
    assert "HIST 50" in out["assistant_reply"]


def test_chinese_natural_language_does_not_trigger_followup():
    prev = {
        "recommended": [{"course": "THTR 189", "units": 5}],
        "total_units": 5,
    }
    out = try_enrichment_followup_plan(
        user_preference="我想要一个中文 enrichment 课。",
        missing_details=[{"requirement": "Educational Enrichment – Courses"}],
        previous_plan=prev,
    )
    assert out is None
