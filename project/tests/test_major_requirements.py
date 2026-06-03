"""Tests for major catalog detection, prereqs, and senior design placement."""

from __future__ import annotations

from utils.major_requirements import (
    build_major_advisor_block,
    detect_major,
    detect_major_detailed,
    enforce_senior_design_in_final_quarters,
    infer_academic_stage,
    load_major_markdown_excerpt,
    next_senior_design_course,
    prerequisites_met,
    remaining_major_courses,
    resolve_major_id,
)


def test_detect_major_detailed_high_confidence_csen() -> None:
    missing = [
        {"requirement": "Computer Science and Engineering Major: CSEN/COEN 194/L"},
        {"requirement": "Major Requirement: CSEN 174"},
    ]
    det = detect_major_detailed(missing)
    assert det["major_id"] == "csen"
    assert det["confidence"] == "high"
    assert "csen" in det["message"].lower() or "Computer" in det["message"]


def test_resolve_major_id_prefers_confirmed() -> None:
    missing = [{"requirement": "Finance Major: FNCE 124"}]
    assert resolve_major_id(confirmed_major_id="csen", missing_details=missing) == "csen"


def test_detect_csen_from_workday_requirement_text() -> None:
    missing = [
        {
            "requirement": "Computer Science and Engineering Major: CSEN/COEN 194/L",
            "status": "Not Satisfied",
            "units": 5,
        },
        {"requirement": "Major Requirement: CSEN 174", "status": "Not Satisfied", "units": 4},
    ]
    assert detect_major(missing) == "csen"


def test_senior_stage_when_upper_division_complete() -> None:
    completed = {"CSEN 174", "CSEN 177", "CSEN 179", "CSEN 122", "CSEN 79"}
    assert infer_academic_stage("csen", completed) == "senior"


def test_next_senior_design_after_174() -> None:
    completed = {"CSEN 174", "CSEN 177", "CSEN 179", "CSEN 192"}
    assert next_senior_design_course("csen", completed) == "CSEN 194"


def test_prerequisites_met_for_csen_174() -> None:
    completed = {"CSEN 79", "CSEN 12", "CSEN 11"}
    assert prerequisites_met("CSEN 174", completed, major_id="csen")


def test_prerequisites_not_met_for_csen_174_without_79() -> None:
    completed = {"CSEN 12", "CSEN 11"}
    assert not prerequisites_met("CSEN 174", completed, major_id="csen")


def test_major_advisor_block_mentions_senior_design() -> None:
    missing = [
        {"requirement": "Computer Science and Engineering Major: CSEN/COEN 195/L", "units": 5},
    ]
    completed = {"CSEN 194", "CSEN 194L", "CSEN 174", "CSEN 177"}
    block, major = build_major_advisor_block(
        missing_details=missing, completed=completed
    )
    assert major == "csen"
    assert "Senior Design" in block
    assert "CSEN 195" in block


def test_remaining_major_courses_excludes_completed() -> None:
    completed = {"CSEN 10", "CSEN 11", "CSEN 12", "ENGR 1"}
    remaining = remaining_major_courses("csen", completed, [])
    assert "CSEN 10" not in remaining
    assert "CSEN 194" in remaining


def test_excerpt_pins_senior_design_sections_when_bulletin_truncated() -> None:
    # CSEN bulletin is ~22KB; default excerpt cap is 10KB, so SD catalog
    # entries and the trailing "## Senior Design sequence" rule live past the
    # cut. They must still reach the LLM prompt.
    text = load_major_markdown_excerpt("csen")
    assert "(… bulletin excerpt truncated …)" in text
    assert "### CSEN 194 —" in text
    assert "### CSEN 195 —" in text
    assert "### CSEN 196 —" in text
    assert "## Senior Design sequence" in text
    assert "one course per quarter in the final year" in text


def test_enforce_senior_design_moves_to_last_three_quarters() -> None:
    plan = {
        "quarters": [
            {
                "term": "Fall 2026",
                "courses": [
                    {"course": "CSEN 194", "units": 4, "title": "SD I", "category": "Major", "reason": "x"},
                    {"course": "CSEN 194L", "units": 1, "title": "SD I Lab", "category": "Major", "reason": "x"},
                    {"course": "COMM 131D", "units": 4, "title": "Comm", "category": "Core", "reason": "y"},
                ],
                "total_units": 9,
            },
            {
                "term": "Winter 2027",
                "courses": [
                    {"course": "CSEN 195", "units": 4, "title": "SD II", "category": "Major", "reason": "x"},
                    {"course": "CSEN 195L", "units": 1, "title": "SD II Lab", "category": "Major", "reason": "x"},
                ],
                "total_units": 5,
            },
            {
                "term": "Spring 2027",
                "courses": [
                    {"course": "CSEN 196", "units": 4, "title": "SD III", "category": "Major", "reason": "x"},
                ],
                "total_units": 4,
            },
            {
                "term": "Fall 2027",
                "courses": [
                    {"course": "CSEN 179", "units": 5, "title": "Algorithms", "category": "Major", "reason": "z"},
                ],
                "total_units": 5,
            },
        ]
    }
    out = enforce_senior_design_in_final_quarters(plan, "csen")
    quarters = out["quarters"]
    # SD was wrongly in Fall 2026; should land in the last three terms only.
    assert "CSEN 194" not in {c["course"] for c in quarters[0]["courses"]}
    last_three = quarters[-3:]
    sd_in_last = []
    for q in last_three:
        for c in q["courses"]:
            code = c["course"]
            if code.startswith("CSEN 19") and "192" not in code:
                sd_in_last.append(code)
    assert "CSEN 194" in sd_in_last
    assert "CSEN 195" in sd_in_last
    assert "CSEN 196" in sd_in_last
