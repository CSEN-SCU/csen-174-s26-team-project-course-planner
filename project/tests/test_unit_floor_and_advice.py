"""Unit-floor enforcement + advice phantom-course scrubbing.

Two production bugs this pins:

1. The planner enforced only a unit CAP, never a FLOOR, so "give me a plan"
   routinely produced an 8-unit schedule (below the 12-unit full-time minimum),
   forcing the student to ask for "more courses". ``_fill_to_min_units`` tops
   the plan up with real next-term candidates until it reaches the floor.

2. The long ``advice`` paragraph was never validated against the final plan,
   so the LLM narrated courses it did not actually schedule ("I recommend
   CSEN 195…", "ENGL 181 fits your load") that were absent from
   ``recommended``. ``_resync_advice`` rewrites advice that presents an
   off-plan course as a recommendation, while preserving legitimate
   "not offered / take it later" deferral guidance.
"""

from __future__ import annotations

from agents.planning_agent import (
    MIN_FULL_TIME_UNITS,
    _advice_has_phantom_recommendation,
    _fill_to_min_units,
    _is_part_time_student,
    _resync_advice,
    _recompute_total_units,
)


def _rec(code, units=4):
    return {"course": code, "units": units, "title": code, "category": "x", "reason": "y"}


# ── _fill_to_min_units ───────────────────────────────────────────────────────


def test_fill_bumps_below_floor_plan_to_minimum():
    """An 8-unit plan is topped up to >= 12 using real candidates."""
    recommended = [_rec("ECEN 153", 4), _rec("ECEN 153L", 1), _rec("ENGR 110", 3)]
    candidates = [("AMTH 118", "Major: AMTH 118"), ("ENGR 111", "Core: RTC 3")]
    out, added = _fill_to_min_units(
        recommended,
        candidates,
        schedule_index={},          # empty → no time conflicts
        units_index=None,           # force the units_lookup fallback
        titles_index=None,
        units_lookup={"AMTH 118": 4, "ENGR 111": 3},
        completed_set=set(),
        min_units=MIN_FULL_TIME_UNITS,
        cap=None,
    )
    assert _recompute_total_units(out) >= MIN_FULL_TIME_UNITS
    assert "AMTH 118" in added  # first candidate alone (8 + 4 = 12) hits the floor


def test_fill_stops_at_floor_does_not_overfill():
    """Once the floor is reached, no further candidates are added."""
    recommended = [_rec("ECEN 153", 4), _rec("ECEN 153L", 1), _rec("ENGR 110", 3)]
    candidates = [("AMTH 118", "x"), ("ENGR 111", "y"), ("MATH 53", "z")]
    out, added = _fill_to_min_units(
        recommended, candidates, {}, None, None,
        {"AMTH 118": 4, "ENGR 111": 3, "MATH 53": 4},
        set(), MIN_FULL_TIME_UNITS, None,
    )
    # 8 + 4 = 12 → stop; ENGR 111 / MATH 53 not needed.
    assert added == ["AMTH 118"]


def test_fill_respects_cap():
    """Never push the total above a stated cap, even if still below the floor."""
    recommended = [_rec("ECEN 153", 4), _rec("ECEN 153L", 1)]  # 5 units
    candidates = [("AMTH 118", "x")]  # +4 = 9, but cap is 6
    out, added = _fill_to_min_units(
        recommended, candidates, {}, None, None,
        {"AMTH 118": 4}, set(), MIN_FULL_TIME_UNITS, cap=6,
    )
    assert added == []  # adding AMTH 118 would exceed the cap
    assert _recompute_total_units(out) == 5


def test_fill_skips_already_present_and_completed():
    recommended = [_rec("ECEN 153", 4), _rec("ECEN 153L", 1), _rec("ENGR 110", 3)]
    candidates = [
        ("ECEN 153", "dup"),       # already present
        ("CSEN 12", "completed"),  # already completed
        ("AMTH 118", "ok"),
    ]
    out, added = _fill_to_min_units(
        recommended, candidates, {}, None, None,
        {"AMTH 118": 4, "CSEN 12": 4},
        {"CSEN 12"}, MIN_FULL_TIME_UNITS, None,
    )
    assert added == ["AMTH 118"]


def test_fill_noop_when_already_at_floor():
    recommended = [_rec("CSEN 122", 4), _rec("CSEN 79", 4), _rec("ENGR 110", 4)]
    out, added = _fill_to_min_units(
        recommended, [("AMTH 118", "x")], {}, None, None,
        {"AMTH 118": 4}, set(), MIN_FULL_TIME_UNITS, None,
    )
    assert added == []
    assert out is recommended


# ── _is_part_time_student (floor exception) ──────────────────────────────────


def test_part_time_detected_english():
    assert _is_part_time_student("I'm a part-time student this quarter")
    assert _is_part_time_student("part time, please keep it light")


def test_part_time_detected_chinese():
    assert _is_part_time_student("我是兼职学生")
    assert _is_part_time_student("我现在非全职")


def test_part_time_not_detected_for_full_time():
    assert not _is_part_time_student("give me a plan")
    assert not _is_part_time_student("我要一个课表")


# ── _advice_has_phantom_recommendation ───────────────────────────────────────


def test_advice_phantom_detected():
    """A course mentioned in advice but absent from the plan is a phantom."""
    assert _advice_has_phantom_recommendation(
        "ENGL 181 is also a required major course that fits within your unit load.",
        {"ECEN 153", "ENGR 110"},
    )


def test_advice_deferral_is_not_phantom():
    """'Not offered / take it later' guidance about an off-plan course is OK."""
    assert not _advice_has_phantom_recommendation(
        "Please note that CSEN 195 is not offered this quarter; plan to take it "
        "when it becomes available.",
        {"ECEN 153", "ENGR 110"},
    )


def test_advice_already_in_plan_is_not_phantom():
    assert not _advice_has_phantom_recommendation(
        "ECEN 153 and ENGR 110 keep you on track.",
        {"ECEN 153", "ENGR 110"},
    )


def test_advice_no_codes_is_not_phantom():
    assert not _advice_has_phantom_recommendation(
        "This plan keeps a balanced full-time load.", {"ECEN 153"}
    )


# ── _resync_advice ───────────────────────────────────────────────────────────


def test_resync_rewrites_phantom_advice():
    parsed = {
        "recommended": [_rec("ECEN 153", 4), _rec("ENGR 110", 3)],
        "total_units": 7,
        "advice": "I recommend taking CSEN 195 and ENGL 181 to round out your load.",
    }
    _resync_advice(parsed)
    # CSEN 195 / ENGL 181 (off-plan) must no longer appear as recommendations.
    assert "CSEN 195" not in parsed["advice"]
    assert "ENGL 181" not in parsed["advice"]
    assert "ECEN 153" in parsed["advice"]


def test_resync_preserves_clean_advice():
    clean = "ECEN 153 and ENGR 110 cover your major and ELSJ requirements nicely."
    parsed = {
        "recommended": [_rec("ECEN 153", 4), _rec("ENGR 110", 3)],
        "total_units": 7,
        "advice": clean,
    }
    _resync_advice(parsed)
    assert parsed["advice"] == clean


def test_resync_preserves_deferral_advice():
    advice = (
        "CSEN 195 is not offered next quarter; plan to take it later. "
        "ECEN 153 keeps you progressing."
    )
    parsed = {
        "recommended": [_rec("ECEN 153", 4)],
        "total_units": 4,
        "advice": advice,
    }
    _resync_advice(parsed)
    assert parsed["advice"] == advice
