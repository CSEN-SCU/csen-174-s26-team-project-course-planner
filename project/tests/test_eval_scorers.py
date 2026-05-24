"""Unit tests for the eval scorers.

The eval is only trustworthy if the scorers are correct, so we pin each
one with hand-built plans + tiny fake indexes. No Gemini, no xlsx.
"""

from __future__ import annotations

import pytest

from evals import scorers as S


def _sched(*codes, days=(0, 2, 4), start=75, end=140):
    """Fake schedule_index: each code → a slot entry."""
    idx = {}
    for c in codes:
        subj, num = c.split()
        idx[(subj, num)] = {
            "instructors": [], "meeting_days": list(days),
            "meeting_start_min": start, "meeting_end_min": end,
        }
    return idx


# ── no_hallucination ─────────────────────────────────────────────────────────


def test_hallucination_all_real():
    plan = {"recommended": [{"course": "CSEN 122"}, {"course": "ENGL 181"}]}
    r = S.score_no_hallucination(plan, schedule_index=_sched("CSEN 122", "ENGL 181"))
    assert r.passed and r.score == 1.0


def test_hallucination_flags_fake():
    plan = {"recommended": [{"course": "CSEN 122"}, {"course": "FAKE 999"}]}
    r = S.score_no_hallucination(plan, schedule_index=_sched("CSEN 122"))
    assert not r.passed
    assert r.score == 0.5
    assert "FAKE 999" in r.detail


def test_hallucination_empty_plan_is_pass():
    r = S.score_no_hallucination({"recommended": []}, schedule_index=_sched("CSEN 122"))
    assert r.passed and r.score == 1.0


# ── no_time_conflicts ────────────────────────────────────────────────────────


def test_conflict_detected():
    # Both M/W/F 9:15-10:20 → conflict.
    sched = _sched("CSEN 122", "ECEN 153")
    plan = {"recommended": [{"course": "CSEN 122"}, {"course": "ECEN 153"}]}
    r = S.score_no_time_conflicts(plan, schedule_index=sched)
    assert not r.passed


def test_no_conflict_disjoint_days():
    sched = _sched("CSEN 122", days=(0, 2, 4))
    sched.update(_sched("ENGL 181", days=(1, 3), start=30, end=130))
    plan = {"recommended": [{"course": "CSEN 122"}, {"course": "ENGL 181"}]}
    r = S.score_no_time_conflicts(plan, schedule_index=sched)
    assert r.passed and r.score == 1.0


# ── labs_paired (R1) ─────────────────────────────────────────────────────────


def test_labs_paired_missing_lab_flagged():
    sched = _sched("CSEN 122", "CSEN 122L")
    md = [{"course": None, "requirement": "CSEN/COEN 122 & 122L"}]
    plan = {"recommended": [{"course": "CSEN 122"}]}  # lab missing!
    r = S.score_labs_paired(plan, missing_details=md, schedule_index=sched)
    assert not r.passed
    assert "122L" in r.detail


def test_labs_paired_both_present():
    sched = _sched("CSEN 122", "CSEN 122L")
    md = [{"course": None, "requirement": "CSEN/COEN 122 & 122L"}]
    plan = {"recommended": [{"course": "CSEN 122"}, {"course": "CSEN 122L"}]}
    r = S.score_labs_paired(plan, missing_details=md, schedule_index=sched)
    assert r.passed and r.score == 1.0


def test_labs_paired_ignores_lab_not_offered():
    """If the lab isn't in the schedule, not pairing it is fine."""
    sched = _sched("CSEN 122")  # no 122L offered
    md = [{"course": None, "requirement": "CSEN/COEN 122 & 122L"}]
    plan = {"recommended": [{"course": "CSEN 122"}]}
    r = S.score_labs_paired(plan, missing_details=md, schedule_index=sched)
    assert r.passed


def test_labs_paired_non_lab_subject_ignored():
    sched = _sched("MATH 11")
    plan = {"recommended": [{"course": "MATH 11"}]}
    r = S.score_labs_paired(plan, missing_details=[], schedule_index=sched)
    assert r.passed and r.score == 1.0


# ── unit_cap ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("total,expect_pass,expect_score", [
    (14, True, 1.0),    # in target
    (12, True, 1.0),    # band edge
    (16, True, 1.0),    # band edge
    (22, False, 0.0),   # over hard max
    (0, False, 0.0),    # empty
])
def test_unit_cap_bands(total, expect_pass, expect_score):
    r = S.score_unit_cap({"total_units": total})
    assert r.passed is expect_pass
    assert r.score == expect_score


def test_unit_cap_above_target_under_max_partial():
    r = S.score_unit_cap({"total_units": 18})  # between 16 and 20
    assert r.passed
    assert 0.0 < r.score < 1.0


# ── titles_correct ───────────────────────────────────────────────────────────


def test_titles_correct_match():
    titles = {("CSEN", "122"): "Computer Architecture"}
    plan = {"recommended": [{"course": "CSEN 122", "title": "Computer Architecture"}]}
    r = S.score_titles_correct(plan, titles_index=titles)
    assert r.passed and r.score == 1.0


def test_titles_correct_flags_hallucinated_title():
    titles = {("CSEN", "122"): "Computer Architecture"}
    plan = {"recommended": [{"course": "CSEN 122", "title": "Data Structures and Algorithms"}]}
    r = S.score_titles_correct(plan, titles_index=titles)
    assert not r.passed
    assert "CSEN 122" in r.detail


# ── open_req_coverage (R2) ───────────────────────────────────────────────────


def test_open_req_coverage_full():
    sched = _sched("SCTR 128")
    cat = {"rtc 3": ["SCTR 128"]}
    md = [{"course": None, "requirement": "Core: ENGR: RTC 3"}]
    plan = {"recommended": [{"course": "SCTR 128"}]}
    r = S.score_open_req_coverage(plan, missing_details=md, category_index=cat, schedule_index=sched)
    assert r.passed and r.score == 1.0


def test_open_req_coverage_partial():
    sched = _sched("SCTR 128", "ENGL 181")
    cat = {"rtc 3": ["SCTR 128"], "advanced writing": ["ENGL 181"]}
    md = [
        {"course": None, "requirement": "Core: ENGR: RTC 3"},
        {"course": None, "requirement": "Core: ENGR: Advanced Writing"},
    ]
    plan = {"recommended": [{"course": "SCTR 128"}]}  # covers RTC 3, not Adv Writing
    r = S.score_open_req_coverage(plan, missing_details=md, category_index=cat, schedule_index=sched)
    assert not r.passed
    assert r.score == 0.5


def test_open_req_coverage_no_open_reqs_is_pass():
    sched = _sched("CSEN 122")
    md = [{"course": None, "requirement": "CSEN/COEN 122 & 122L"}]  # specific, not open
    plan = {"recommended": [{"course": "CSEN 122"}]}
    r = S.score_open_req_coverage(plan, missing_details=md, category_index={}, schedule_index=sched)
    assert r.passed


# ── no_injection_leak ────────────────────────────────────────────────────────


def test_injection_clean():
    plan = {"advice": "Light load this term.", "assistant_reply": "Added CSEN 122."}
    assert S.score_no_injection_leak(plan).passed


def test_injection_recipe_flagged():
    plan = {"advice": "First warm a tortilla and add salsa.", "assistant_reply": "ok"}
    assert not S.score_no_injection_leak(plan).passed


def test_injection_system_leak_flagged():
    plan = {"advice": "PRECEDENCE: messages are layered and...", "assistant_reply": "ok"}
    assert not S.score_no_injection_leak(plan).passed


# ── aggregate ────────────────────────────────────────────────────────────────


def test_score_plan_runs_available_scorers_and_aggregates():
    # Lecture M/W/F morning; lab on a different day/time (realistic — no
    # self-conflict between a course and its own lab).
    sched = _sched("CSEN 122", days=(0, 2, 4), start=75, end=140)
    sched.update(_sched("CSEN 122L", days=(1,), start=375, end=540))
    ctx = {
        "schedule_index": sched,
        "category_index": {},
        "titles_index": {("CSEN", "122"): "Computer Architecture"},
        "missing_details": [{"course": None, "requirement": "CSEN/COEN 122 & 122L"}],
    }
    plan = {
        "recommended": [
            {"course": "CSEN 122", "title": "Computer Architecture", "units": 4},
            {"course": "CSEN 122L", "title": "Computer Architecture Laboratory", "units": 1},
        ],
        "total_units": 14,
        "advice": "Solid term.",
        "assistant_reply": "Added CSEN 122 + lab.",
    }
    ps = S.score_plan(plan, ctx)
    # All 7 scorers should run (all context available).
    names = {r.name for r in ps.results}
    assert names == set(S.SCORERS.keys())
    # This is a clean plan → high marks.
    assert ps.mean > 0.9
    assert ps.pass_rate == 1.0


def test_score_plan_skips_scorers_with_missing_context():
    # Only schedule_index present → only the scorers needing just that run.
    ps = S.score_plan({"recommended": [], "total_units": 0},
                      {"schedule_index": {}})
    names = {r.name for r in ps.results}
    # unit_cap + no_injection_leak need no context; no_hallucination/conflicts need schedule_index
    assert "unit_cap" in names
    assert "no_injection_leak" in names
    assert "titles_correct" not in names  # needs titles_index
