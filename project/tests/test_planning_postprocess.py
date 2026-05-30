"""Post-processing for plans: completed-course filter, units, lab pairing."""

from __future__ import annotations

from agents import planning_agent
from utils.academic_progress_helpers import (
    enrich_missing_details,
    extract_completed_course_codes,
)


def test_extract_completed_from_parsed_rows():
    rows = [
        {"course_code": "CSEN 10", "status": "Satisfied", "units": 4},
        {"course_code": "MATH 51", "status": "Not Satisfied", "units": 4},
    ]
    done = extract_completed_course_codes(rows)
    assert "CSEN 10" in done
    assert "MATH 51" not in done


def test_filter_removes_completed_recommendations():
    recs = [
        {"course": "CSEN 10", "units": 4, "category": "Core", "reason": "x"},
        {"course": "CSEN 122", "units": 4, "category": "Major", "reason": "y"},
    ]
    kept, removed = planning_agent._filter_completed_recommendations(recs, {"CSEN 10"})
    assert len(kept) == 1
    assert kept[0]["course"] == "CSEN 122"
    assert "CSEN 10" in removed


def test_standalone_lab_swapped_to_lecture():
    recs = [{"course": "CSEN 122L", "units": 1, "category": "Major", "reason": "lab only"}]
    out = planning_agent._prefer_lecture_over_standalone_lab(recs)
    assert out[0]["course"] == "CSEN 122"


def test_enrich_units_defaults_lecture_and_lab():
    lookup = {}
    recs = [{"course": "CSEN 174", "units": 0}, {"course": "CSEN 174L", "units": None}]
    out = planning_agent._enrich_recommended_units(recs, lookup)
    assert out[0]["units"] == 4
    assert out[1]["units"] == 1


def test_pair_lab_uses_units_lookup():
    md = [{"requirement": "CSEN/COEN 122 & 122L"}]
    recs = [{"course": "CSEN 122", "units": 4, "category": "Major", "reason": "lec"}]
    lookup = {"CSEN 122": 4, "CSEN 122L": 1}
    paired = planning_agent._pair_lab_corequirements(recs, md, units_lookup=lookup)
    codes = {i["course"] for i in paired}
    assert "CSEN 122" in codes
    assert "CSEN 122L" in codes
    lab = next(i for i in paired if i["course"].endswith("122L"))
    assert lab["units"] == 1


def test_enrich_missing_details_adds_units():
    md = [{"requirement": "CSEN/COEN 122 & 122L", "status": "Not Satisfied"}]
    rows = [
        {
            "requirement": "CSEN/COEN 122 & 122L",
            "status": "Not Satisfied",
            "course_code": None,
            "units": 5,
        }
    ]
    out = enrich_missing_details(md, rows)
    assert out[0].get("units") == 5


def test_enrich_csen_junior_requirements_not_and_codes():
    """Regression: 'Computer Science and Engineering' must not yield AND 122."""
    md = [
        {
            "requirement": (
                "Computer Science and Engineering Major: CSEN/COEN 122 & 122L"
            ),
            "status": "Not Satisfied",
        },
        {
            "requirement": "Computer Science and Engineering Major: CSEN/COEN 174",
            "status": "Not Satisfied",
        },
        {"requirement": "University Core: RTC 3", "status": "Not Satisfied"},
        {"requirement": "University Core: Advanced Writing", "status": "Not Satisfied"},
    ]
    out = enrich_missing_details(md, [])
    assert out[0]["course"] == "CSEN 122"
    assert out[1]["course"] == "CSEN 174"
    assert not out[2].get("course")  # RTC 3 is a Core tag, not a catalog code
    assert not out[3].get("course")


def test_resolve_item_codes_prefers_extraction_over_stale_course_field():
    from agents.planning_agent import _resolve_item_codes

    item = {
        "course": "AND 122",
        "requirement": "Computer Science and Engineering Major: CSEN/COEN 122 & 122L",
    }
    codes = _resolve_item_codes(item)
    assert "CSEN 122" in codes
    assert "COEN 122" in codes
    assert "AND 122" not in codes
