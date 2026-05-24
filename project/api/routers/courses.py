"""Course catalog listing for the manual "+ Add course" picker.

GET /api/courses          → {"courses": [ {course, title, units, professor,
                            meeting_days, meeting_start_min, meeting_end_min,
                            lab_partner}, ... ]}
POST /api/courses/refresh → drop the catalog caches so a replaced schedule
                            xlsx is served without a server restart.

The list is the next-term schedule (from the Find Course Sections xlsx),
deduplicated by (subject, number). The frontend fetches it once and
filters client-side; selecting a course adds it directly to the plan
without an LLM round-trip. The result is cached at process scope, so when
the schedule xlsx is replaced the cache must be invalidated via /refresh.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from fastapi import APIRouter

from utils.scu_course_schedule_xlsx import clear_caches as clear_schedule_caches
from utils.scu_course_schedule_xlsx import list_offered_courses

router = APIRouter()


@lru_cache(maxsize=1)
def _cached_courses() -> list[dict[str, Any]]:
    return list_offered_courses()


@router.get("")
def get_courses() -> dict[str, Any]:
    courses = _cached_courses()
    return {"courses": courses, "count": len(courses)}


@router.post("/refresh")
def refresh_courses() -> dict[str, Any]:
    """Invalidate the course caches so an updated schedule xlsx is picked up
    without restarting the server, then re-read and report the new count.

    PROTOTYPE: intentionally unauthenticated. In production this endpoint MUST
    be protected (admin token / internal-only access) — it forces a disk
    re-read of the schedule xlsx and should not be open to anonymous callers.
    """
    _cached_courses.cache_clear()
    clear_schedule_caches()
    courses = _cached_courses()
    return {"refreshed": True, "count": len(courses)}
