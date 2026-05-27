from agents.four_year_planning_agent import (
    FOUR_YEAR_TERM_COUNT,
    _drop_empty_quarters,
    _generate_term_sequence,
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

