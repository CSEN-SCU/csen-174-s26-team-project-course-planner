from agents.four_year_planning_agent import (
    FOUR_YEAR_TERM_COUNT,
    _MAX_COURSES_PER_QUARTER,
    _drop_empty_quarters,
    _enforce_course_count_cap,
    _estimate_quarter_budget,
    _generate_term_sequence,
    _has_senior_design,
)


def test_four_year_term_count_is_12() -> None:
    assert FOUR_YEAR_TERM_COUNT == 12


def test_generate_term_sequence_length_and_uniqueness() -> None:
    terms = _generate_term_sequence("Fall", 2026, FOUR_YEAR_TERM_COUNT)
    assert len(terms) == FOUR_YEAR_TERM_COUNT
    assert len(set(terms)) == FOUR_YEAR_TERM_COUNT
    assert terms[0] == "Fall 2026"


def test_drop_empty_quarters_removes_empties_and_updates_graduation_term() -> None:
    plan = {
        "quarters": [
            {"term": "Fall 2026", "courses": [], "total_units": 0},
            {
                "term": "Winter 2027",
                "courses": [{"course": "CSEN 10", "title": "Intro", "category": "Major", "units": 4, "reason": "x"}],
                "total_units": 4,
            },
            {"term": "Spring 2027", "courses": [], "total_units": 0},
        ],
        "graduation_term": "Spring 2027",
        "total_remaining_units": 4,
        "advice": "",
    }
    out = _drop_empty_quarters(plan)
    assert [q["term"] for q in out["quarters"]] == ["Winter 2027"]
    assert out["graduation_term"] == "Winter 2027"


# ── Senior Design detection ──────────────────────────────────────────────────


def test_has_senior_design_detects_csen_194() -> None:
    assert _has_senior_design([{"requirement": "CSEN 194"}])


def test_has_senior_design_detects_slash_subjects_and_labs() -> None:
    assert _has_senior_design([{"requirement": "CSEN/COEN 195 & 195L"}])
    assert _has_senior_design([{"category": "Major: COEN 196L"}])


def test_has_senior_design_false_when_absent() -> None:
    assert not _has_senior_design([{"requirement": "CSEN 122"}])
    assert not _has_senior_design([])


# ── Quarter budget ───────────────────────────────────────────────────────────


def test_budget_packs_small_remaining_into_few_quarters() -> None:
    # 22 units, senior design present → 3 consecutive quarters required, target 3.
    budget = _estimate_quarter_budget(total_units=22, has_senior_design=True)
    assert budget["min_quarters"] == 3
    assert budget["target_quarters"] == 3
    # Allow at most one slack quarter so the LLM cannot spray courses across 6+.
    assert budget["max_quarters"] <= 4


def test_budget_no_senior_design_small_load_uses_2_quarters() -> None:
    # 16 units, no senior design → 2 quarters fits comfortably.
    budget = _estimate_quarter_budget(total_units=16, has_senior_design=False)
    assert budget["target_quarters"] <= 2
    assert budget["max_quarters"] <= 3


def test_budget_caps_at_four_years() -> None:
    # Even with very heavy remaining load, never exceed 12 quarters.
    budget = _estimate_quarter_budget(total_units=300, has_senior_design=True)
    assert budget["max_quarters"] <= FOUR_YEAR_TERM_COUNT


def test_budget_zero_units_no_senior_design_is_one_quarter() -> None:
    budget = _estimate_quarter_budget(total_units=0, has_senior_design=False)
    assert budget["min_quarters"] >= 1
    assert budget["max_quarters"] >= 1


# ── Course-count budget (prevents cramming when units are missing) ───────────


def test_budget_course_count_prevents_cramming_when_units_missing() -> None:
    # Workday gap rows often lack a units field, so total_units underestimates
    # to ~0. Course count must still force a sane number of quarters: 16 courses
    # at a 4/quarter target (and a 5/quarter hard cap) needs at least 4 quarters.
    budget = _estimate_quarter_budget(
        total_units=0, total_courses=16, has_senior_design=False
    )
    assert budget["min_quarters"] >= 4  # ceil(16 / 5)
    assert budget["target_quarters"] >= 4  # ceil(16 / 4)


def test_budget_course_count_dominates_low_unit_load() -> None:
    # 20 low-unit courses but only 24 units. Units alone would suggest ~2
    # quarters; course count must win so we don't cram 10/quarter.
    budget = _estimate_quarter_budget(
        total_units=24, total_courses=20, has_senior_design=False
    )
    assert budget["target_quarters"] >= 5  # ceil(20 / 4)


def test_budget_course_count_default_is_backward_compatible() -> None:
    # Omitting total_courses must not change prior units-only behavior.
    budget = _estimate_quarter_budget(total_units=22, has_senior_design=True)
    assert budget["target_quarters"] == 3
    assert budget["max_quarters"] <= 4


# ── Per-quarter course cap enforcement ───────────────────────────────────────


def _course(code: str, units: int = 4) -> dict:
    return {"course": code, "title": code, "category": "Major", "units": units, "reason": "x"}


def test_enforce_course_count_cap_spills_overflow_to_next_quarter() -> None:
    plan = {
        "quarters": [
            {
                "term": "Fall 2026",
                "courses": [_course(f"CSEN {10 + i}") for i in range(8)],
                "total_units": 32,
            },
        ],
        "graduation_term": "Fall 2026",
    }
    out = _enforce_course_count_cap(plan)
    assert all(len(q["courses"]) <= _MAX_COURSES_PER_QUARTER for q in out["quarters"])
    total = sum(len(q["courses"]) for q in out["quarters"])
    assert total == 8  # no course dropped
    assert len(out["quarters"]) >= 2  # overflow spilled forward
    assert out["quarters"][1]["term"] == "Winter 2027"


def test_enforce_course_count_cap_keeps_lab_with_lecture() -> None:
    courses = (
        [_course(f"MATH {11 + i}") for i in range(4)]
        + [_course("CSEN 20"), _course("CSEN 20L", 1), _course("PHYS 31")]
    )
    plan = {
        "quarters": [{"term": "Fall 2026", "courses": courses, "total_units": 22}],
        "graduation_term": "Fall 2026",
    }
    out = _enforce_course_count_cap(plan)
    total = sum(len(q["courses"]) for q in out["quarters"])
    assert total == 7
    for q in out["quarters"]:
        codes = [c["course"] for c in q["courses"]]
        assert len(codes) <= _MAX_COURSES_PER_QUARTER
        # A lecture and its lab must never be split across quarters (R1).
        if "CSEN 20" in codes or "CSEN 20L" in codes:
            assert "CSEN 20" in codes and "CSEN 20L" in codes


def test_enforce_course_count_cap_no_change_when_within_cap() -> None:
    plan = {
        "quarters": [
            {"term": "Fall 2026", "courses": [_course("CSEN 10"), _course("MATH 11")], "total_units": 8},
        ],
        "graduation_term": "Fall 2026",
    }
    out = _enforce_course_count_cap(plan)
    assert len(out["quarters"]) == 1
    assert [c["course"] for c in out["quarters"][0]["courses"]] == ["CSEN 10", "MATH 11"]

