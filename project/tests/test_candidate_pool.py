"""Closed-world candidate pool builder for the constrained planner.

Pins:
  - concrete requirements become Major:<code> must-cover labels;
  - open Core requirements aggregate when one course satisfies many of
    them (R2 double tagging);
  - lab partners are auto-added with a lab_partner_id cross-reference
    so the selector can pair them (R1);
  - completed courses are excluded;
  - courses not offered next term are excluded;
  - LLM projection contains only fields the LLM can safely see.
"""

from __future__ import annotations

from agents.candidate_pool import (
    CandidateCourse,
    SectionOption,
    build_candidate_pool,
)


def _section(num, days, start, end, instructor=None, rating=None, difficulty=None):
    return {
        "section": num,
        "meeting_days": list(days),
        "meeting_start_min": start,
        "meeting_end_min": end,
        "instructors": [instructor] if instructor else [],
    }


def _sched_entry(days, start, end, instructors=()):
    return {
        "instructors": list(instructors),
        "meeting_days": list(days),
        "meeting_start_min": start,
        "meeting_end_min": end,
    }


# ── concrete-requirement pool ────────────────────────────────────────────────


def test_pool_concrete_requirements_become_major_labels():
    sched = {
        ("CSEN", "174"): _sched_entry([0, 2, 4], 75, 140, ("Smith",)),
        ("COEN", "174"): _sched_entry([0, 2, 4], 75, 140, ("Smith",)),
        ("MATH", "53"): _sched_entry([1, 3], 200, 290, ("Doe",)),
    }
    titles = {
        ("CSEN", "174"): "Software Engineering",
        ("COEN", "174"): "Software Engineering",
        ("MATH", "53"): "Linear Algebra",
    }
    units = {
        ("CSEN", "174"): 4,
        ("COEN", "174"): 4,
        ("MATH", "53"): 4,
    }
    all_secs = {
        ("CSEN", "174"): [_section(1, [0, 2, 4], 75, 140, "Smith")],
        ("COEN", "174"): [_section(1, [0, 2, 4], 75, 140, "Smith")],
        ("MATH", "53"): [_section(1, [1, 3], 200, 290, "Doe")],
    }
    candidates, must_cover = build_candidate_pool(
        missing_details=[
            {"course": "CSEN 174", "category": "Major"},
            {"course": "MATH 53", "category": "Major"},
        ],
        completed_codes=set(),
        schedule_index=sched,
        category_index={},
        titles_index=titles,
        units_index=units,
        all_sections=all_secs,
        ratings={},
    )
    codes = {c.course_code for c in candidates}
    assert codes == {"CSEN 174", "MATH 53"}
    assert sorted(must_cover) == ["Major: CSEN 174", "Major: MATH 53"]
    # Titles + units come from canonical xlsx, never from the missing_details row.
    by_code = {c.course_code: c for c in candidates}
    assert by_code["CSEN 174"].title == "Software Engineering"
    assert by_code["CSEN 174"].units == 4


def test_pool_excludes_completed_courses():
    sched = {("CSEN", "174"): _sched_entry([0], None, None)}
    candidates, must_cover = build_candidate_pool(
        missing_details=[{"course": "CSEN 174", "category": "Major"}],
        completed_codes={"CSEN 174"},
        schedule_index=sched,
        category_index={},
        titles_index={},
        units_index={},
        all_sections={},
        ratings={},
    )
    assert candidates == []
    # The label is still added so the engine can surface it as deferred.
    # (Caller decides; pool just doesn't return a candidate to pick.)


def test_pool_excludes_courses_not_offered_next_term():
    candidates, must_cover = build_candidate_pool(
        missing_details=[{"course": "CSEN 174", "category": "Major"}],
        completed_codes=set(),
        schedule_index={},  # empty schedule → nothing offered
        category_index={},
        titles_index={},
        units_index={},
        all_sections={},
        ratings={},
    )
    assert candidates == []


def test_pool_skips_educational_enrichment_requirement():
    """v2 candidate pool ignores Educational Enrichment — students choose it."""
    sched = {
        ("THTR", "189"): _sched_entry([1, 3], 200, 290),
        ("CSEN", "174"): _sched_entry([0, 2, 4], 75, 140),
    }
    category_index = {
        "educational enrichment": ["THTR 189", "GNSX 115"],
    }
    candidates, must_cover = build_candidate_pool(
        missing_details=[
            {"course": "CSEN 174", "category": "Major"},
            {
                "requirement": (
                    "Computer Science and Engineering Major: "
                    "Educational Enrichment – Courses"
                ),
            },
        ],
        completed_codes=set(),
        schedule_index=sched,
        category_index=category_index,
        titles_index={
            ("CSEN", "174"): "Software Engineering",
            ("THTR", "189"): "Theatre and Society",
        },
        units_index={("CSEN", "174"): 4, ("THTR", "189"): 5},
        all_sections={
            ("CSEN", "174"): [_section(1, [0, 2, 4], 75, 140, "Smith")],
            ("THTR", "189"): [_section(1, [1, 3], 200, 290, "Jones")],
        },
        ratings={},
    )
    codes = {c.course_code for c in candidates}
    assert codes == {"CSEN 174"}
    assert must_cover == ["Major: CSEN 174"]
    assert "educational enrichment" not in must_cover


# ── open Core requirements + double tagging ─────────────────────────────────


def test_pool_aggregates_categories_for_double_tagged_course():
    """SCTR 128 satisfies three Core requirements at once (R2 example).

    Mirrors production: ``load_category_course_index`` keys the same
    course under BOTH the short tag ("rtc 3") and the long description
    ("religion, theology and culture 3"). Workday exports the long form
    in the requirement category text, so the resolver matches on the
    long key.
    """
    sched = {("SCTR", "128"): _sched_entry([0, 2], 200, 265)}
    category_index = {
        "rtc 3": ["SCTR 128"],
        "religion, theology and culture 3": ["SCTR 128"],
        "elsj": ["SCTR 128"],
        "experiential learning for social justice": ["SCTR 128"],
        "applied ethics": ["SCTR 128"],
    }
    candidates, must_cover = build_candidate_pool(
        missing_details=[
            {"category": "Core: ENGR: RTC 3", "requirement": "Core: ENGR: RTC 3"},
            {"category": "Core: ENGR: Experiential Learning for Social Justice",
             "requirement": "Core: ENGR: Experiential Learning for Social Justice"},
            {"category": "Core: ENGR: Applied Ethics",
             "requirement": "Core: ENGR: Applied Ethics"},
        ],
        completed_codes=set(),
        schedule_index=sched,
        category_index=category_index,
        titles_index={("SCTR", "128"): "Religion, Violence, Nonviolence"},
        units_index={("SCTR", "128"): 4},
        all_sections={("SCTR", "128"): [_section(1, [0, 2], 200, 265, "Doe")]},
        ratings={},
    )
    assert len(candidates) == 1
    cand = candidates[0]
    assert cand.course_code == "SCTR 128"
    assert cand.double_tagged is True
    assert len(cand.categories_satisfied) == 3
    assert "rtc 3" in cand.categories_satisfied
    assert "experiential learning for social justice" in cand.categories_satisfied
    assert "applied ethics" in cand.categories_satisfied
    # All three open requirements must appear in must_cover so the
    # selector knows what to satisfy.
    assert set(must_cover) >= {"rtc 3", "experiential learning for social justice", "applied ethics"}


# ── lab partner auto-add ─────────────────────────────────────────────────────


def test_pool_auto_adds_lab_partner_with_cross_referenced_id():
    sched = {
        ("CSEN", "122"): _sched_entry([0, 2, 4], 75, 140),
        ("CSEN", "122L"): _sched_entry([2], 375, 540),
    }
    candidates, _ = build_candidate_pool(
        missing_details=[{"course": "CSEN 122", "category": "Major"}],
        completed_codes=set(),
        schedule_index=sched,
        category_index={},
        titles_index={
            ("CSEN", "122"): "Computer Architecture",
            ("CSEN", "122L"): "Computer Architecture Laboratory",
        },
        units_index={("CSEN", "122"): 4, ("CSEN", "122L"): 1},
        all_sections={
            ("CSEN", "122"): [_section(1, [0, 2, 4], 75, 140, "Smith")],
            ("CSEN", "122L"): [_section(1, [2], 375, 540, "Smith")],
        },
        ratings={},
    )
    by_code = {c.course_code: c for c in candidates}
    assert {"CSEN 122", "CSEN 122L"} <= set(by_code)
    assert by_code["CSEN 122"].lab_partner_id == by_code["CSEN 122L"].id
    assert by_code["CSEN 122L"].lab_partner_id == by_code["CSEN 122"].id
    assert by_code["CSEN 122L"].kind == "lab_companion"


def test_pool_does_not_add_lab_partner_when_not_offered():
    sched = {("CSEN", "122"): _sched_entry([0, 2, 4], 75, 140)}
    candidates, _ = build_candidate_pool(
        missing_details=[{"course": "CSEN 122", "category": "Major"}],
        completed_codes=set(),
        schedule_index=sched,
        category_index={},
        titles_index={},
        units_index={},
        all_sections={("CSEN", "122"): [_section(1, [0, 2, 4], 75, 140)]},
        ratings={},
    )
    assert [c.course_code for c in candidates] == ["CSEN 122"]
    assert candidates[0].lab_partner_id is None


# ── section options + best-section ratings ──────────────────────────────────


def test_pool_best_section_prefers_highest_rated_instructor():
    sched = {("CSEN", "174"): _sched_entry([0], 75, 140)}
    all_secs = {
        ("CSEN", "174"): [
            _section(1, [0, 2, 4], 75, 140, "Low"),
            _section(2, [1, 3], 200, 265, "High"),
            _section(3, [4], 300, 365, "Mid"),
        ],
    }
    ratings = {
        "Low": {"rating": 2.0, "difficulty": 4.0},
        "High": {"rating": 4.7, "difficulty": 2.5},
        "Mid": {"rating": 3.5, "difficulty": 3.0},
    }
    candidates, _ = build_candidate_pool(
        missing_details=[{"course": "CSEN 174", "category": "Major"}],
        completed_codes=set(),
        schedule_index=sched,
        category_index={},
        titles_index={},
        units_index={("CSEN", "174"): 4},
        all_sections=all_secs,
        ratings=ratings,
    )
    cand = candidates[0]
    best = cand.best_section
    assert best is not None
    assert best.instructor == "High"
    assert best.instructor_rating == 4.7


# ── LLM projection schema ───────────────────────────────────────────────────


def test_to_llm_projection_exposes_safe_fields_only():
    sched = {("CSEN", "174"): _sched_entry([0], 75, 140)}
    candidates, _ = build_candidate_pool(
        missing_details=[{"course": "CSEN 174", "category": "Major"}],
        completed_codes=set(),
        schedule_index=sched,
        category_index={},
        titles_index={("CSEN", "174"): "Software Engineering"},
        units_index={("CSEN", "174"): 4},
        all_sections={("CSEN", "174"): [_section(1, [0], 75, 140, "Smith")]},
        ratings={"Smith": {"rating": 4.0, "difficulty": 3.0}},
    )
    proj = candidates[0].to_llm_projection()
    assert proj["id"] == 0
    assert proj["code"] == "CSEN 174"
    assert proj["title"] == "Software Engineering"
    assert proj["units"] == 4
    assert proj["covers"] == ["Major: CSEN 174"]
    assert proj["covers_count"] == 1
    assert proj["double_tagged"] is False
    assert proj["best_instructor"] == "Smith"
    assert proj["best_rating"] == 4.0
    # Sections array length only — never raw meeting times to the LLM.
    assert proj["sections"] == 1
    assert "meeting_days" not in proj
    assert "meeting_start_min" not in proj
