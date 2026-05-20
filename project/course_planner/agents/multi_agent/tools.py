"""Tools the multi-agent graph can call.

Each tool is a *deterministic* function (no LLM inside) that wraps an
existing utility in ``utils.scu_course_schedule_xlsx`` or
``agents.planning_agent``. The LLM-driven graph nodes decide *when* to
call them; the tools themselves are dumb data accessors.

This separation is the key value LangGraph adds for this project: agent
nodes do reasoning, tools do lookups, and the graph routes between them.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

# Import existing helpers — do NOT reimplement.
from agents.planning_agent import (
    _normalize_open_req_text,
    _resolve_open_requirement,
)
from utils.scu_course_schedule_xlsx import (
    all_sections_for_course,
    course_title_for,
    detect_time_conflicts,
    instructor_rating_for,
    load_all_course_sections,
    load_category_course_index,
    load_course_titles_index,
    load_instructor_ratings,
    load_schedule_section_index,
    planned_section_keys,
)

# ── Lazy loaders cached at process scope ─────────────────────────────────────


@lru_cache(maxsize=1)
def _schedule_index() -> dict:
    return load_schedule_section_index()


@lru_cache(maxsize=1)
def _category_index() -> dict[str, list[str]]:
    return load_category_course_index()


@lru_cache(maxsize=1)
def _titles_index() -> dict[tuple[str, str], str]:
    return load_course_titles_index()


@lru_cache(maxsize=1)
def _all_sections() -> dict[tuple[str, str], list[dict]]:
    return load_all_course_sections()


# ── Tools: search ────────────────────────────────────────────────────────────


def tool_search_schedule(subject: str | None = None) -> list[dict[str, Any]]:
    """Return a flat list of courses in next-term schedule, optionally
    filtered by subject prefix (e.g. ``"CSEN"``).

    Each entry: ``{"course": "CSEN 122", "title": "Computer Architecture",
    "instructors": [...], "meeting_days": [...], "start_min": int,
    "end_min": int}``.
    """
    sched = _schedule_index()
    titles = _titles_index()
    out: list[dict[str, Any]] = []
    for (subj, num), entry in sched.items():
        if subject and subj.upper() != subject.upper():
            continue
        code = f"{subj} {num}"
        out.append(
            {
                "course": code,
                "title": course_title_for(code, titles),
                "instructors": list(entry.get("instructors") or []),
                "meeting_days": list(entry.get("meeting_days") or []),
                "start_min": entry.get("meeting_start_min"),
                "end_min": entry.get("meeting_end_min"),
            }
        )
    return out


def tool_get_open_req_candidates(requirement_text: str) -> dict[str, Any]:
    """For an open Core/GE requirement (e.g. ``"Core: ENGR: RTC 3"``),
    return the candidate courses in next-term schedule that satisfy it,
    plus the normalized requirement label."""
    sched = _schedule_index()
    cat = _category_index()
    titles = _titles_index()
    label = _normalize_open_req_text(requirement_text) or requirement_text[:40]
    candidates = _resolve_open_requirement(requirement_text, cat, sched)
    enriched = [
        {"course": c, "title": course_title_for(c, titles)} for c in candidates
    ]
    return {"label": label, "candidates": enriched}


def tool_get_lab_partner(course_code: str) -> str | None:
    """Return the lab co-requirement code (e.g. ``"CSEN 122L"``) for a
    lecture, or vice versa. ``None`` if the subject has no lab pair rule
    or the partner isn't in next-term schedule."""
    parts = course_code.upper().strip().split()
    if len(parts) != 2:
        return None
    subj, num = parts
    LAB_SUBJECTS = {"CSEN", "COEN", "CSCI", "ELEN", "ECEN", "PHYS", "CHEM", "BIOL", "MECH"}
    if subj not in LAB_SUBJECTS:
        return None
    partner_num = num[:-1] if num.endswith("L") else num + "L"
    partner = f"{subj} {partner_num}"
    sched = _schedule_index()
    if any(k in sched for k in planned_section_keys(partner)):
        return partner
    return None


# ── Tools: verification ──────────────────────────────────────────────────────


def tool_check_in_schedule(course_code: str) -> bool:
    """True if the course is in the published next-term schedule."""
    sched = _schedule_index()
    return any(k in sched for k in planned_section_keys(course_code))


def tool_detect_conflicts(course_codes: list[str]) -> list[tuple[int, int, str, str]]:
    """Return (idx_a, idx_b, code_a, code_b) for every overlapping pair."""
    sched = _schedule_index()
    pairs = detect_time_conflicts(course_codes, sched)
    return [(a, b, course_codes[a], course_codes[b]) for (a, b) in pairs]


def tool_score_double_tag_coverage(
    plan_courses: list[str], open_requirements: list[str]
) -> dict[str, Any]:
    """How many open requirements does the plan cover, and how many of
    its courses are double-tagged?"""
    cat = _category_index()
    sched = _schedule_index()
    covered: set[str] = set()
    multi_tag_courses: list[str] = []
    for code in plan_courses:
        tags_for_this_course: set[str] = set()
        for req in open_requirements:
            cands = _resolve_open_requirement(req, cat, sched)
            if code in cands:
                tags_for_this_course.add(_normalize_open_req_text(req) or req[:40])
        covered |= tags_for_this_course
        if len(tags_for_this_course) > 1:
            multi_tag_courses.append(code)
    return {
        "total_open_reqs": len(open_requirements),
        "covered": sorted(covered),
        "uncovered": [
            _normalize_open_req_text(r) or r[:40]
            for r in open_requirements
            if (_normalize_open_req_text(r) or r[:40]) not in covered
        ],
        "double_tag_picks": multi_tag_courses,
    }


# ── Tools: instructor selection ──────────────────────────────────────────────


def tool_get_sections(course_code: str) -> list[dict[str, Any]]:
    """All sections of ``course_code`` in next-term schedule."""
    return all_sections_for_course(course_code, _all_sections())


@lru_cache(maxsize=1)
def _ratings() -> dict[str, dict[str, Any]]:
    return load_instructor_ratings()


def tool_get_instructor_rating(instructor_name: str) -> dict[str, Any]:
    """Return a rating dict for an instructor from data/instructor_ratings.csv.

    Falls back to ``rating=None, source="unavailable"`` for instructors we
    have no data on, so the picker degrades gracefully instead of crashing.
    """
    return instructor_rating_for(instructor_name, _ratings())


def tool_compare_instructors(names: list[str]) -> list[dict[str, Any]]:
    """Side-by-side comparison for the instructor selector to surface
    in the final plan response."""
    return [tool_get_instructor_rating(n) for n in names]


# Registry so the agent nodes (and tests) can introspect available tools.
ALL_TOOLS = {
    "search_schedule": tool_search_schedule,
    "get_open_req_candidates": tool_get_open_req_candidates,
    "get_lab_partner": tool_get_lab_partner,
    "check_in_schedule": tool_check_in_schedule,
    "detect_conflicts": tool_detect_conflicts,
    "score_double_tag_coverage": tool_score_double_tag_coverage,
    "get_sections": tool_get_sections,
    "get_instructor_rating": tool_get_instructor_rating,
    "compare_instructors": tool_compare_instructors,
}
