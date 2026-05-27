from agents.four_year_planning_agent import (
    FOUR_YEAR_TERM_COUNT,
    _drop_empty_quarters,
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

