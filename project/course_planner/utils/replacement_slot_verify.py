"""Verify calendar-driven replacements against Find Course Sections meeting patterns."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from utils.course_variants import extract_course_variants
from utils.meeting_pattern_parse import parse_schedule

# Column order matches ``main.py`` weekday grid (Monday..Friday).
_COLUMN_DAY_TOKENS: tuple[tuple[str, ...], ...] = (
    ("M",),
    ("T",),
    ("W",),
    ("Th", "R"),
    ("F",),
)


def _norm_course_key(s: str) -> str:
    return " ".join(str(s or "").split()).upper()


def _parse_clock_to_minutes(clock: str) -> Optional[int]:
    s = " ".join(str(clock or "").split())
    if not s:
        return None
    s = s.upper().replace("AM", " AM").replace("PM", " PM")
    s = " ".join(s.split())
    for fmt in ("%I:%M %p", "%H:%M"):
        try:
            dt = datetime.strptime(s.strip(), fmt)
            return dt.hour * 60 + dt.minute
        except ValueError:
            continue
    return None


def _interval_overlap_mins(a0: int, a1: int, b0: int, b1: int) -> bool:
    """Inclusive overlap on a closed timeline (same calendar day)."""
    return a0 <= b1 and b0 <= a1


def _column_day_matches(col_i: int, day_token: str) -> bool:
    if col_i < 0 or col_i >= len(_COLUMN_DAY_TOKENS):
        return False
    d = str(day_token or "").strip()
    return d in _COLUMN_DAY_TOKENS[col_i]


def _vacated_day_tokens_for_column(col_i: int, vacated: dict[str, Any]) -> set[str]:
    """Day letters from the removed course that fall in this weekday column."""
    out: set[str] = set()
    for d in vacated.get("days") or []:
        if _column_day_matches(col_i, str(d)):
            out.add(str(d))
    return out


def _patterns_for_course(base_map: dict[str, str], course_str: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    if not base_map:
        return out
    for v in extract_course_variants(course_str):
        key = _norm_course_key(v)
        raw = base_map.get(key)
        if raw and str(raw).strip() and str(raw) not in seen:
            seen.add(str(raw))
            out.append(str(raw).strip())
    return out


def gap_category_for_course(gaps: list[dict], course_str: str) -> str:
    """Best-effort match of a plan course string to a gap row's requirement label."""
    variants = {_norm_course_key(v) for v in extract_course_variants(course_str)}
    for g in gaps or []:
        if not isinstance(g, dict):
            continue
        gc = (g.get("course") or "").strip()
        if not gc:
            continue
        gv = {_norm_course_key(v) for v in extract_course_variants(gc)}
        if variants & gv:
            return str(g.get("category") or "").strip() or "—"
    return "—"


def slot_matches_vacated_window(
    vacated_col_i: int,
    vacated_parsed: dict[str, Any],
    candidate_raw: str,
) -> bool:
    """True if ``candidate_raw`` parses to a meeting that hits the same column day and overlaps times."""
    vac_days = _vacated_day_tokens_for_column(vacated_col_i, vacated_parsed)
    if not vac_days:
        return False
    v0 = _parse_clock_to_minutes(str(vacated_parsed.get("start") or ""))
    v1 = _parse_clock_to_minutes(str(vacated_parsed.get("end") or ""))
    if v0 is None or v1 is None:
        return False
    if v0 > v1:
        v0, v1 = v1, v0

    cand = parse_schedule(candidate_raw)
    if not cand:
        return False
    cand_days = {str(d) for d in (cand.get("days") or [])}
    if not (cand_days & vac_days):
        return False
    c0 = _parse_clock_to_minutes(str(cand.get("start") or ""))
    c1 = _parse_clock_to_minutes(str(cand.get("end") or ""))
    if c0 is None or c1 is None:
        return False
    if c0 > c1:
        c0, c1 = c1, c0
    return _interval_overlap_mins(v0, v1, c0, c1)


def new_recommended_courses(
    old_recommended: list[dict],
    new_recommended: list[dict],
    removed_display: str,
) -> list[str]:
    """Course display strings that appear in ``new`` but not ``old`` (excluding removed)."""
    old_set = {_norm_course_key((x or {}).get("course")) for x in old_recommended if isinstance(x, dict)}
    removed_n = _norm_course_key(removed_display)
    seen: set[str] = set()
    out: list[str] = []
    for x in new_recommended or []:
        if not isinstance(x, dict):
            continue
        raw_c = (x.get("course") or "").strip()
        cn = _norm_course_key(raw_c)
        if not cn or cn == removed_n:
            continue
        if cn in old_set or cn in seen:
            continue
        seen.add(cn)
        out.append(raw_c or cn)
    return out


def verify_calendar_replacements(
    *,
    old_plan: dict[str, Any],
    new_plan: dict[str, Any],
    gaps: list[dict],
    removed_course: str,
    vacated_col_i: Optional[int],
    vacated_parsed: Optional[dict[str, Any]],
    base_schedule_map: dict[str, str],
) -> list[dict[str, Any]]:
    """Build table rows describing each newly introduced course vs xlsx + vacated slot."""
    old_recs = old_plan.get("recommended") or []
    new_recs = new_plan.get("recommended") or []
    added = new_recommended_courses(old_recs, new_recs, removed_course)
    rows: list[dict[str, Any]] = []
    for course in added:
        cats = gap_category_for_course(gaps, course)
        pats = _patterns_for_course(base_schedule_map, course)
        has_xlsx = bool(pats)
        slot_ok: Optional[bool] = None
        note = ""
        if vacated_parsed is None or vacated_col_i is None:
            slot_ok = None
            note = "Vacated time unknown — skipped slot overlap check."
        elif not has_xlsx:
            slot_ok = False
            note = "No Meeting Patterns row in Find Course Sections for this code (variant keys)."
        else:
            slot_ok = any(
                slot_matches_vacated_window(vacated_col_i, vacated_parsed, raw) for raw in pats
            )
            if not slot_ok:
                note = (
                    "Found section row(s), but no parsed pattern matched this weekday column "
                    "with overlapping clock times vs the removed course."
                )
            else:
                note = "At least one workbook pattern matches the vacated weekday + overlapping time."

        rows.append(
            {
                "New course": course,
                "Gap requirement": cats,
                "In Find Course Sections": "yes" if has_xlsx else "no",
                "Slot fits vacated window": (
                    "yes"
                    if slot_ok is True
                    else ("no" if slot_ok is False else "n/a")
                ),
                "Sample Meeting Patterns": (pats[0][:120] + "…") if pats and len(pats[0]) > 120 else (pats[0] if pats else "—"),
                "Notes": note,
            }
        )
    if not rows:
        rows.append(
            {
                "New course": "—",
                "Gap requirement": "—",
                "In Find Course Sections": "—",
                "Slot fits vacated window": "n/a",
                "Sample Meeting Patterns": "—",
                "Notes": "No new course codes vs the previous plan (model may have only removed or reshuffled existing codes).",
            }
        )
    return rows
