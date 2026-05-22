"""Course catalog listing for the manual "+ Add course" picker.

GET /api/courses  → {"courses": [ {course, title, units, professor,
                    meeting_days, meeting_start_min, meeting_end_min,
                    lab_partner}, ... ]}

The list is the next-term schedule (from the Find Course Sections xlsx),
deduplicated by (subject, number). The frontend fetches it once and
filters client-side; selecting a course adds it directly to the plan
without an LLM round-trip.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from fastapi import APIRouter

from utils.scu_course_schedule_xlsx import list_offered_courses

router = APIRouter()


@lru_cache(maxsize=1)
def _cached_courses() -> list[dict[str, Any]]:
    return list_offered_courses()


@router.get("")
def get_courses() -> dict[str, Any]:
    courses = _cached_courses()
    return {"courses": courses, "count": len(courses)}
