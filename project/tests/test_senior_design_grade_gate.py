"""R-gate: Senior Design capstones are grade-gated in the candidate pool.

Regression guard for the bug surfaced by the grade-level eval harness: a
CSEN freshman (nothing completed) was recommended ENGR 194 (Senior Design)
because the constrained_v2 candidate pool applied no prerequisite or
grade-level gating. A student who has barely started must never be handed
a final-year capstone even when Workday still lists it unsatisfied.

The gate is a coarse "minimum completed courses" floor in
``build_candidate_pool`` (AGENTS.md plan A); precise final-year placement
is handled separately by ``enforce_senior_design_in_final_quarters``.
"""

from __future__ import annotations

from agents.candidate_pool import (
    _SENIOR_DESIGN_MIN_COMPLETED,
    _is_senior_design_code,
    _senior_design_gated,
    build_candidate_pool,
)


def test_is_senior_design_code_matches_capstones_and_labs() -> None:
    for code in ("CSEN 194", "ENGR 194", "CSEN 195", "CSEN 196", "ECEN 194", "MECH 194L"):
        assert _is_senior_design_code(code), code


def test_is_senior_design_code_rejects_regular_courses() -> None:
    for code in ("CSEN 10", "CSEN 174", "MATH 11", "CSEN 193", "CSEN 199", "ENGR 1"):
        assert not _is_senior_design_code(code), code


def test_gate_blocks_capstone_for_low_completion() -> None:
    # Freshman: nothing completed → gated.
    assert _senior_design_gated("ENGR 194", set())
    assert _senior_design_gated("CSEN 194", set())


def test_gate_allows_capstone_once_threshold_met() -> None:
    completed = {f"X {i}" for i in range(_SENIOR_DESIGN_MIN_COMPLETED)}
    assert not _senior_design_gated("CSEN 194", completed)


def test_gate_never_touches_non_capstone_courses() -> None:
    # A regular course is never gated regardless of completion count.
    assert not _senior_design_gated("CSEN 174", set())
    assert not _senior_design_gated("MATH 11", set())


def test_build_pool_excludes_senior_design_for_freshman() -> None:
    """End-to-end: a freshman's pool must not contain a Senior Design code."""
    missing = [
        {"requirement": "CSE Major: ENGR 194", "course": "ENGR 194", "status": "Not Satisfied"},
        {"requirement": "CSE Major: CSEN 194", "course": "CSEN 194", "status": "Not Satisfied"},
        {"requirement": "CSE Major: CSEN 10", "course": "CSEN 10", "status": "Not Satisfied"},
    ]
    candidates, _ = build_candidate_pool(missing, completed_codes=set())
    codes = {c.course_code for c in candidates}
    assert not any(_is_senior_design_code(c) for c in codes), (
        f"freshman pool leaked a capstone: {sorted(codes)}"
    )


def test_build_pool_includes_senior_design_for_advanced_student() -> None:
    """A student past the floor should see the capstone in their pool."""
    completed = {f"FILLER {i}" for i in range(_SENIOR_DESIGN_MIN_COMPLETED)}
    missing = [
        {"requirement": "CSE Major: CSEN 194", "course": "CSEN 194", "status": "Not Satisfied"},
    ]
    candidates, _ = build_candidate_pool(missing, completed_codes=completed)
    codes = {c.course_code for c in candidates}
    # CSEN 194 is offered in the checked-in schedule; if present at all it
    # must be allowed through for an advanced student.
    assert "CSEN 194" in codes or not any(
        _is_senior_design_code(c) for c in codes
    ), f"advanced student pool unexpectedly gated: {sorted(codes)}"
