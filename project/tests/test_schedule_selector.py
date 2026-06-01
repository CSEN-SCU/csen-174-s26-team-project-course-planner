"""Deterministic schedule selector (PR3).

Hard constraints + soft scoring pinned. Builds tiny CandidateCourse
fixtures by hand so tests stay independent of the xlsx loader.
"""

from __future__ import annotations

from agents.candidate_pool import CandidateCourse, SectionOption
from agents.schedule_selector import select_schedule


def _sec(num, days, start, end, instructor=None, rating=None, difficulty=None):
    return SectionOption(
        section_number=num,
        meeting_days=tuple(days),
        meeting_start_min=start,
        meeting_end_min=end,
        instructor=instructor,
        instructor_rating=rating,
        instructor_difficulty=difficulty,
    )


def _cand(idx, code, units, cats, sections, *, is_lab=False, lab_partner_id=None):
    return CandidateCourse(
        id=idx,
        course_code=code,
        title=code,
        units=units,
        categories_satisfied=tuple(cats),
        sections=tuple(sections),
        is_lab=is_lab,
        lab_partner_code=None,
        lab_partner_id=lab_partner_id,
        kind="required_specific",
    )


# ── coverage + double-tagging ────────────────────────────────────────────────


def test_selector_prioritizes_major_courses_over_extra_ge_fillers():
    """When unit budget is tight, pick offered major courses before packing
    additional unrelated GE electives."""
    csen = _cand(
        0, "CSEN 174", 4, ["Major: CSEN 174"],
        [_sec(1, [0, 2, 4], 75, 140, rating=4.0)],
    )
    math = _cand(
        1, "MATH 53", 4, ["Major: MATH 53"],
        [_sec(1, [1, 3], 200, 265, rating=4.0)],
    )
    sctr = _cand(
        2, "SCTR 128", 4,
        ["rtc 3", "elsj", "applied ethics"],
        [_sec(1, [0, 2], 200, 265, rating=4.5)],
    )
    engl = _cand(3, "ENGL 1A", 4, ["arts"], [_sec(1, [4], 300, 365, rating=3.5)])
    phil = _cand(4, "PHIL 9", 4, ["advanced writing"], [_sec(1, [4], 200, 265, rating=3.5)])

    result = select_schedule(
        [sctr, engl, phil, csen, math],
        must_cover=[
            "Major: CSEN 174",
            "Major: MATH 53",
            "rtc 3",
            "elsj",
            "applied ethics",
            "arts",
            "advanced writing",
        ],
        unit_min=12,
        unit_max=16,
        hard_max=16,
    )
    codes = {c.course_code for c in result.selected}
    assert {"CSEN 174", "MATH 53"} <= codes
    assert sum(c.units for c in result.selected) <= 16


def test_selector_prefers_double_tagged_candidate():
    """SCTR 128 covers 3 Core slots in one course; should win over
    picking 3 single-coverage courses."""
    sctr = _cand(
        0, "SCTR 128", 4,
        ["rtc 3", "elsj", "applied ethics"],
        [_sec(1, [0, 2], 200, 265, rating=4.5)],
    )
    rtc_alt = _cand(1, "RSOC 12", 4, ["rtc 3"], [_sec(1, [1, 3], 200, 265, rating=3.5)])
    elsj_alt = _cand(2, "ANTH 50", 4, ["elsj"], [_sec(1, [1, 3], 300, 365, rating=3.5)])
    ethics_alt = _cand(3, "PHIL 26", 4, ["applied ethics"], [_sec(1, [4], 200, 265, rating=3.5)])
    csen174 = _cand(4, "CSEN 174", 4, ["Major: CSEN 174"], [_sec(1, [0, 2, 4], 75, 140, rating=4.0)])

    result = select_schedule(
        [sctr, rtc_alt, elsj_alt, ethics_alt, csen174],
        must_cover=["rtc 3", "elsj", "applied ethics", "Major: CSEN 174"],
        unit_min=8, unit_max=12, hard_max=14,
    )
    codes = {c.course_code for c in result.selected}
    assert codes == {"SCTR 128", "CSEN 174"}
    assert result.deferred == []


# ── time conflicts ──────────────────────────────────────────────────────────


def test_selector_rejects_time_conflicts():
    """Two courses with identical M/W/F 9:15 slots can't coexist; the
    selector must pick exactly one and defer the other's requirement."""
    a = _cand(0, "CSEN 122", 4, ["Major: CSEN 122"], [_sec(1, [0, 2, 4], 75, 140, rating=4.0)])
    b = _cand(1, "ECEN 153", 4, ["Major: ECEN 153"], [_sec(1, [0, 2, 4], 75, 140, rating=4.0)])
    c = _cand(2, "MATH 53", 4, ["Major: MATH 53"], [_sec(1, [1, 3], 200, 265, rating=4.0)])
    result = select_schedule(
        [a, b, c],
        must_cover=["Major: CSEN 122", "Major: ECEN 153", "Major: MATH 53"],
        unit_min=8, unit_max=12, hard_max=14,
    )
    codes = {c.course_code for c in result.selected}
    # At least one of CSEN 122 / ECEN 153 will be deferred; MATH 53 must
    # be picked because it doesn't conflict.
    assert "MATH 53" in codes
    assert not ({"CSEN 122", "ECEN 153"} <= codes)
    deferred_labels = {d["requirement"] for d in result.deferred}
    assert "Major: CSEN 122" in deferred_labels or "Major: ECEN 153" in deferred_labels


def test_selector_picks_alternative_section_to_avoid_conflict():
    """When CSEN 174 has two sections and one conflicts with MATH 53,
    the selector picks the non-conflicting section."""
    csen = _cand(
        0, "CSEN 174", 4, ["Major: CSEN 174"],
        [
            _sec(1, [1, 3], 200, 265, rating=4.5),     # T/Th 11:20-12:25 — conflicts with MATH below
            _sec(2, [0, 2, 4], 75, 140, rating=4.0),   # M/W/F 9:15-10:20 — no conflict
        ],
    )
    math = _cand(1, "MATH 53", 4, ["Major: MATH 53"], [_sec(1, [1, 3], 200, 265, rating=4.0)])
    result = select_schedule(
        [csen, math],
        must_cover=["Major: CSEN 174", "Major: MATH 53"],
        unit_min=6, unit_max=10, hard_max=12,
    )
    codes = {c.course_code for c in result.selected}
    assert codes == {"CSEN 174", "MATH 53"}
    csen_sec = result.chosen_sections[csen.id]
    assert csen_sec.section_number == 2  # the non-conflicting one


# ── lab pairing (R1) ─────────────────────────────────────────────────────────


def test_selector_pairs_lecture_and_lab():
    lec = _cand(0, "CSEN 122", 4, ["Major: CSEN 122"], [_sec(1, [0, 2, 4], 75, 140, rating=4.0)])
    lab = _cand(1, "CSEN 122L", 1, ["Major: CSEN 122"], [_sec(1, [2], 375, 540, rating=4.0)], is_lab=True)
    lec.lab_partner_id = 1
    lab.lab_partner_id = 0
    filler = _cand(2, "MATH 53", 4, ["Major: MATH 53"], [_sec(1, [1, 3], 200, 265, rating=4.0)])
    extra = _cand(3, "ENGL 1A", 4, ["Major: ENGL 1A"], [_sec(1, [1, 3], 300, 365, rating=4.0)])
    result = select_schedule(
        [lec, lab, filler, extra],
        must_cover=["Major: CSEN 122", "Major: MATH 53"],
        unit_min=12, unit_max=13, hard_max=14,
    )
    codes = {c.course_code for c in result.selected}
    # Lecture and lab MUST appear together; never one alone.
    assert ("CSEN 122" in codes) == ("CSEN 122L" in codes)
    assert {"CSEN 122", "CSEN 122L"} <= codes


# ── unit cap ─────────────────────────────────────────────────────────────────


def test_selector_respects_hard_max():
    a = _cand(0, "CSEN 174", 4, ["Major: CSEN 174"], [_sec(1, [0, 2, 4], 75, 140, rating=4.0)])
    b = _cand(1, "MATH 53", 4, ["Major: MATH 53"], [_sec(1, [1, 3], 200, 265, rating=4.0)])
    c = _cand(2, "ENGR 110", 4, ["Major: ENGR 110"], [_sec(1, [4], 200, 265, rating=4.0)])
    d = _cand(3, "ENGL 1A", 4, ["Major: ENGL 1A"], [_sec(1, [1, 3], 300, 365, rating=4.0)])
    e = _cand(4, "PHIL 9", 4, ["Major: PHIL 9"], [_sec(1, [0, 2], 300, 365, rating=4.0)])
    result = select_schedule(
        [a, b, c, d, e],
        must_cover=["Major: CSEN 174", "Major: MATH 53", "Major: ENGR 110", "Major: ENGL 1A", "Major: PHIL 9"],
        unit_min=12, unit_max=16, hard_max=16,
    )
    total = sum(c.units for c in result.selected)
    assert total <= 16
    assert total >= 12


def test_selector_returns_empty_when_no_feasible_plan():
    a = _cand(0, "CSEN 174", 20, ["Major: CSEN 174"], [_sec(1, [0], 75, 140, rating=4.0)])
    result = select_schedule(
        [a],
        must_cover=["Major: CSEN 174"],
        unit_min=12, unit_max=16, hard_max=16,
    )
    assert result.selected == []
    assert result.deferred and result.deferred[0]["requirement"] == "Major: CSEN 174"


# ── preference scoring ──────────────────────────────────────────────────────


def test_selector_honors_no_morning_preference():
    """When 'no morning' is in the preference and two sections exist,
    the afternoon section wins even with similar ratings."""
    csen = _cand(
        0, "CSEN 174", 4, ["Major: CSEN 174"],
        [
            _sec(1, [0, 2, 4], 30, 95, rating=4.0),    # 8:30-9:35 AM
            _sec(2, [0, 2, 4], 240, 305, rating=4.0),  # 12:00-1:05 PM
        ],
    )
    result = select_schedule(
        [csen],
        must_cover=["Major: CSEN 174"],
        user_preference="no morning classes please",
        unit_min=4, unit_max=4, hard_max=4,
    )
    sec = result.chosen_sections[csen.id]
    assert sec.section_number == 2


def test_selector_avoids_explicit_mwf_1030_even_with_better_rated_morning_section():
    """User says no MWF at 10:30 — pick the 1pm section even if morning has
    a higher-rated instructor."""
    csen = _cand(
        0, "CSEN 174", 4, ["Major: CSEN 174"],
        [
            _sec(1, [0, 2, 4], 150, 225, rating=4.8),   # M/W/F 10:30
            _sec(2, [0, 2, 4], 300, 375, rating=4.0),  # M/W/F 1:00 PM
        ],
    )
    result = select_schedule(
        [csen],
        must_cover=["Major: CSEN 174"],
        user_preference="I do not want a MWF class at 10:30",
        unit_min=4, unit_max=4, hard_max=4,
    )
    assert result.chosen_sections[csen.id].section_number == 2


# ── R7 locked codes ─────────────────────────────────────────────────────────


def test_selector_respects_locked_codes_for_followup():
    locked = _cand(0, "CSEN 174", 4, ["Major: CSEN 174"], [_sec(1, [0, 2, 4], 75, 140, rating=4.0)])
    new = _cand(1, "MATH 53", 4, ["Major: MATH 53"], [_sec(1, [1, 3], 200, 265, rating=4.0)])
    other = _cand(2, "ENGL 1A", 4, ["Major: ENGL 1A"], [_sec(1, [1, 3], 300, 365, rating=4.0)])
    result = select_schedule(
        [locked, new, other],
        must_cover=["Major: CSEN 174", "Major: MATH 53"],
        unit_min=8, unit_max=12, hard_max=14,
        locked_codes={"CSEN 174"},
    )
    codes = {c.course_code for c in result.selected}
    assert "CSEN 174" in codes  # never dropped because locked
    assert "MATH 53" in codes  # filled in around the lock
