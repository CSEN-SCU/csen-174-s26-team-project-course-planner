"""Eval scenarios + shared context loader.

A scenario is a realistic planning request (missing_details + preference)
with a human-readable name. The context bundles the schedule / category /
title indexes the scorers need; it's loaded once and reused.

The default scenario set is derived from the checked-in sample transcript
(View_My_Academic_Progress.xlsx) plus a few synthetic edge cases.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from utils.academic_progress_xlsx import parse_academic_progress_xlsx
from utils.scu_course_schedule_xlsx import (
    load_all_course_sections,
    load_category_course_index,
    load_course_titles_index,
    load_course_units_index,
    load_schedule_section_index,
)


@dataclass
class Scenario:
    name: str
    missing_details: list[dict[str, Any]]
    user_preference: str = ""
    notes: str = ""


@lru_cache(maxsize=1)
def load_context() -> dict[str, Any]:
    """Indexes the scorers need. Cached for the whole eval run."""
    return {
        "schedule_index": load_schedule_section_index(),
        "category_index": load_category_course_index(),
        "titles_index": load_course_titles_index(),
        "units_index": load_course_units_index(),
        "all_sections": load_all_course_sections(),
    }


@lru_cache(maxsize=1)
def _sample_missing_details() -> list[dict[str, Any]]:
    """Remaining requirements from the checked-in sample transcript."""
    from pathlib import Path

    xlsx = Path(__file__).resolve().parents[1] / "View_My_Academic_Progress.xlsx"
    if not xlsx.is_file():
        return []
    data = parse_academic_progress_xlsx(xlsx.read_bytes())
    return data.get("not_satisfied") or []


def default_scenarios() -> list[Scenario]:
    md = _sample_missing_details()
    return [
        Scenario(
            name="sample_balanced",
            missing_details=md,
            user_preference="Balanced load, finish core requirements, no early classes.",
            notes="Real sample transcript; general preference.",
        ),
        Scenario(
            name="sample_light_load",
            missing_details=md,
            user_preference="Light quarter, at most 13 units, prioritize Senior Design.",
            notes="Unit-cap pressure + Senior Design sequencing.",
        ),
        Scenario(
            name="sample_core_first",
            missing_details=md,
            user_preference="Knock out as many Core/GE requirements as possible this term.",
            notes="Stresses open-requirement coverage + double-tagging.",
        ),
        Scenario(
            name="empty_requirements",
            missing_details=[],
            user_preference="plan my next quarter",
            notes="Degenerate: nothing to plan → engine should not hallucinate.",
        ),
    ]


def scenario_context(scenario: Scenario) -> dict[str, Any]:
    """Per-scenario scorer context = global indexes + this scenario's
    missing_details."""
    ctx = dict(load_context())
    ctx["missing_details"] = scenario.missing_details
    return ctx
