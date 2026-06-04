from agents.four_year_planning_agent import (
    FOUR_YEAR_TERM_COUNT,
    _HARD_UNIT_CAP_PER_QUARTER,
    _MAX_COURSES_PER_QUARTER,
    _TARGET_UNITS_PER_QUARTER,
    _distribute_placeholders,
    _drop_empty_quarters,
    _enforce_course_count_cap,
    _enforce_sequential_core_pairs,
    _estimate_quarter_budget,
    _generate_term_sequence,
    _has_senior_design,
    _is_pseudo_course_code,
    _latest_in_progress_term,
    _parse_academic_period,
    _requirement_display_label,
)


def test_parse_academic_period_formats() -> None:
    assert _parse_academic_period("Fall 2026") == "Fall 2026"
    assert _parse_academic_period("Fall 2026 Quarter") == "Fall 2026"
    assert _parse_academic_period("2025-2026 Winter Quarter") == "Winter 2026"
    assert _parse_academic_period("2025-2026 Fall Quarter") == "Fall 2025"
    assert _parse_academic_period("Spring 2026-2027") == "Spring 2026"
    assert _parse_academic_period("nonsense") is None


def test_expand_partial_requirement_gaps_adds_ud_and_enrichment_slots() -> None:
    from utils.academic_progress_helpers import expand_partial_requirement_gaps

    ud_req = (
        "Computer Science and Engineering Major: 3 UD Courses including associated labs"
    )
    enrich_req = "Computer Science and Engineering Major: Educational Enrichment - Courses"
    parsed = [
        {
            "requirement": ud_req,
            "status": "In Progress",
            "course_code": "CSEN 163",
        },
        {
            "requirement": ud_req,
            "status": "In Progress",
            "course_code": "CSEN 163L",
        },
    ]
    missing = [{"requirement": enrich_req, "remaining": "Minimum Combination Required"}]
    out = expand_partial_requirement_gaps(missing, parsed)
    assert sum(1 for m in out if "3 ud courses" in str(m.get("requirement", "")).lower()) == 2
    assert sum(1 for m in out if "educational enrichment" in str(m.get("requirement", "")).lower()) == 3


def test_latest_in_progress_term_picks_max_enrolled_quarter() -> None:
    rows = [
        {"status": "Satisfied", "academic_period": "Spring 2024"},
        {"status": "In Progress", "academic_period": "Fall 2023"},
        {"status": "In Progress", "academic_period": "Fall 2026"},
    ]
    assert _latest_in_progress_term(rows) == "Fall 2026"
    assert _latest_in_progress_term([]) is None
    assert _latest_in_progress_term(
        [{"status": "Satisfied", "academic_period": "Spring 2024"}]
    ) is None


def test_requirement_display_label_strips_prefixes() -> None:
    assert _requirement_display_label("Core: ENGR: University Core") == "University Core"
    assert (
        _requirement_display_label("Core: ENGR: Critical Thinking & Writing 2")
        == "Critical Thinking & Writing 2"
    )


def test_distribute_placeholders_fills_lightest_quarter_under_cap() -> None:
    plan = {
        "quarters": [
            {"term": "Fall 2026", "courses": [{"course": "CSEN 174", "units": 4}], "total_units": 4},
            {"term": "Winter 2027", "courses": [], "total_units": 0},
        ]
    }
    ph = [{"course": "University Core", "title": "University Core (choose a course)",
           "category": "University Core", "units": 4, "reason": "x", "placeholder": True}]
    out = _distribute_placeholders(plan, ph, max_courses=_MAX_COURSES_PER_QUARTER)
    winter = next(q for q in out["quarters"] if q["term"] == "Winter 2027")
    assert any(c["course"] == "University Core" for c in winter["courses"])
    assert winter["total_units"] == 4


def test_hard_unit_cap_is_20() -> None:
    assert _HARD_UNIT_CAP_PER_QUARTER == 20


def test_sequential_core_pair_derives_level2_next_quarter() -> None:
    """Cultures & Ideas 2 is the same subject as level 1, +1 number, next term."""
    plan = {
        "quarters": [
            {
                "term": "Fall 2026",
                "courses": [
                    {
                        "course": "HIST 11A",
                        "title": "World History",
                        "category": "Core: ENGR: Cultures & Ideas 1",
                        "units": 4,
                        "reason": "x",
                    }
                ],
                "total_units": 4,
            },
            {"term": "Winter 2027", "courses": [], "total_units": 0},
        ]
    }
    missing = [
        {"requirement": "Core: ENGR: Cultures & Ideas 1", "course": "IDEAS 1", "units": 4},
        {"requirement": "Core: ENGR: Cultures & Ideas 2", "course": "IDEAS 2", "units": 4},
    ]
    out = _enforce_sequential_core_pairs(plan, missing)
    winter = next(q for q in out["quarters"] if q["term"] == "Winter 2027")
    derived = [c for c in winter["courses"] if c["course"] == "HIST 12A"]
    assert derived, "level-2 course must be derived as HIST 12A in the next quarter"
    assert derived[0]["title"] == "World History"


def test_four_year_term_count_is_12() -> None:
    assert FOUR_YEAR_TERM_COUNT == 12


def test_target_units_per_quarter_is_18() -> None:
    """SCU full-time engineering quarters are ~18 units; the budget must aim
    there so plans pack realistically instead of spilling into a 5th year."""
    assert _TARGET_UNITS_PER_QUARTER == 18


def test_pseudo_course_code_detects_workday_placeholders() -> None:
    assert _is_pseudo_course_code("IDEAS 1") is True
    assert _is_pseudo_course_code("ideas 2") is True
    assert _is_pseudo_course_code("CSEN 122") is False
    assert _is_pseudo_course_code("CSEN 194L") is False
    assert _is_pseudo_course_code("") is False


def test_budget_targets_fewer_quarters_at_18_units() -> None:
    """~62 remaining units / 16 courses should fit in ~4 quarters, not 5."""
    budget = _estimate_quarter_budget(
        total_units=62, total_courses=16, has_senior_design=True
    )
    assert budget["target_quarters"] == 4


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

