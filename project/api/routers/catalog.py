"""Section-level course catalog for the manual course browser."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from utils.scu_course_schedule_xlsx import (
    _cached_offered_sections,
    _find_schedule_path,
    catalog_facets,
    clear_schedule_caches,
    enrich_section_instructor_rating,
    filter_catalog_sections,
    list_offered_sections,
    load_instructor_ratings,
    sort_catalog_sections,
)

router = APIRouter()


@lru_cache(maxsize=1)
def _all_sections() -> tuple[dict[str, Any], ...]:
    path = _find_schedule_path(None)
    key = str(path) if path else None
    return _cached_offered_sections(key)


def _parse_csv_ints(raw: str | None) -> list[int]:
    if not raw or not raw.strip():
        return []
    out: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.append(int(part))
        except ValueError:
            continue
    return out


def _parse_csv_strs(raw: str | None) -> list[str]:
    if not raw or not raw.strip():
        return []
    return [p.strip() for p in raw.split(",") if p.strip()]


@router.get("/sections")
def search_catalog_sections(
    q: str | None = Query(None),
    subject: str | None = Query(None, description="Comma-separated course subjects"),
    days: str | None = Query(None, description="Comma-separated weekday indices 0=Mon"),
    meeting_time: str | None = Query(
        None,
        description="Comma-separated meeting_time slot ids (days:start:end)",
    ),
    tag: str | None = Query(None, description="Comma-separated requirement tags"),
    day_index: int | None = Query(None, ge=0, le=4),
    start_min: int | None = Query(None, ge=0),
    end_min: int | None = Query(None, ge=0),
    sort: str | None = Query(
        None,
        description="Sort: default, rating (quality desc), difficulty (easier first), balanced",
    ),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    """Search next-term sections with Workday-style filters."""
    if _find_schedule_path(None) is None:
        raise HTTPException(
            status_code=503,
            detail="Course catalog unavailable (SCU_Find_Course_Sections.xlsx missing on server).",
        )

    all_sections = list(_all_sections())
    filtered = filter_catalog_sections(
        all_sections,
        q=q,
        subjects=_parse_csv_strs(subject),
        days=_parse_csv_ints(days),
        meeting_time_slots=_parse_csv_strs(meeting_time),
        tags=_parse_csv_strs(tag),
        day_index=day_index,
        start_min=start_min,
        end_min=end_min,
    )
    ratings = load_instructor_ratings()
    enriched = [enrich_section_instructor_rating(s, ratings) for s in filtered]
    sorted_rows = sort_catalog_sections(enriched, sort)
    total = len(sorted_rows)
    page = sorted_rows[offset : offset + limit]
    facets = catalog_facets(all_sections)

    return {
        "sections": page,
        "total": total,
        "count": len(page),
        "offset": offset,
        "facets": facets,
    }


@router.post("/refresh")
def refresh_catalog() -> dict[str, Any]:
    """Clear section catalog caches after the schedule xlsx is replaced."""
    clear_schedule_caches()
    _all_sections.cache_clear()
    from routers import courses as courses_router

    courses_router._cached_courses.cache_clear()
    sections = list(_all_sections())
    return {"ok": True, "count": len(sections)}
