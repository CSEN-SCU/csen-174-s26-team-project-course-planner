"""Helpers for academic progress rows → planner inputs."""

from __future__ import annotations

import re
from typing import Any

from utils.scu_course_schedule_xlsx import planned_section_keys

_COURSE_CODE_RE = re.compile(r"^([A-Z]{2,6})\s+(\d{1,3}[A-Z]?)$", re.IGNORECASE)

_COMPLETED_STATUSES = frozenset({"satisfied", "in progress"})

_DEFAULT_LECTURE_UNITS = 4
_DEFAULT_LAB_UNITS = 1


def _normalize_code(code: str | None) -> str:
    return (code or "").strip().upper()


def _parse_units(raw: Any) -> int | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, (int, float)):
        u = int(raw)
        return u if u > 0 else None
    try:
        u = int(float(str(raw).strip()))
        return u if u > 0 else None
    except (TypeError, ValueError):
        return None


def extract_completed_course_codes(parsed_rows: list[dict[str, Any]] | None) -> set[str]:
    """Course codes the student has already taken or is currently taking."""
    completed: set[str] = set()
    for row in parsed_rows or []:
        if not isinstance(row, dict):
            continue
        code = _normalize_code(row.get("course_code"))
        if not code:
            continue
        status = str(row.get("status") or "").strip().lower()
        if status not in _COMPLETED_STATUSES:
            continue
        completed.add(code)
        for subj, num in planned_section_keys(code):
            completed.add(f"{subj} {num}".upper())
    return completed


def build_units_lookup(
    missing_details: list[dict[str, Any]] | None,
    parsed_rows: list[dict[str, Any]] | None,
) -> dict[str, int]:
    """Best-effort map of course code → units from transcript + gap rows."""
    lookup: dict[str, int] = {}

    for row in parsed_rows or []:
        if not isinstance(row, dict):
            continue
        code = _normalize_code(row.get("course_code"))
        units = _parse_units(row.get("units"))
        if code and units:
            lookup[code] = max(lookup.get(code, 0), units)

    for item in missing_details or []:
        if not isinstance(item, dict):
            continue
        units = _parse_units(item.get("units"))
        if not units:
            continue
        explicit = _normalize_code(item.get("course"))
        if explicit:
            lookup[explicit] = max(lookup.get(explicit, 0), units)
        req = str(item.get("requirement") or item.get("category") or "")
        for m in re.finditer(r"\b([A-Z]{2,6})\s+(\d{1,3}[A-Z]?)\b", req.upper()):
            c = f"{m.group(1)} {m.group(2)}"
            lookup[c] = max(lookup.get(c, 0), units)

    return lookup


def default_units_for_code(code: str, lookup: dict[str, int]) -> int:
    norm = _normalize_code(code)
    if norm in lookup:
        return lookup[norm]
    m = _COURSE_CODE_RE.match(norm)
    if m and m.group(2).endswith("L"):
        return _DEFAULT_LAB_UNITS
    return _DEFAULT_LECTURE_UNITS


def enrich_missing_details(
    missing_details: list[dict[str, Any]] | None,
    parsed_rows: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Attach units (and a hint course code) to Workday-style gap rows."""
    if not missing_details:
        return []

    units_by_requirement: dict[str, int] = {}
    for row in parsed_rows or []:
        if not isinstance(row, dict):
            continue
        rq = str(row.get("requirement") or "").strip()
        units = _parse_units(row.get("units"))
        if rq and units:
            units_by_requirement[rq] = max(units_by_requirement.get(rq, 0), units)

    lookup = build_units_lookup(missing_details, parsed_rows)
    out: list[dict[str, Any]] = []
    for item in missing_details:
        if not isinstance(item, dict):
            continue
        row = dict(item)
        rq = str(row.get("requirement") or "").strip()
        if rq in units_by_requirement and not _parse_units(row.get("units")):
            row["units"] = units_by_requirement[rq]
        if not _normalize_code(row.get("course")) and rq:
            nums = re.findall(r"\b(\d{1,3}[A-Z]?)\b", rq.upper())
            subjs = re.findall(r"\b([A-Z]{2,6})\b", rq.upper())
            if subjs and nums:
                row.setdefault("course", f"{subjs[0]} {nums[0]}")
        code = _normalize_code(row.get("course"))
        if code and not _parse_units(row.get("units")):
            row["units"] = default_units_for_code(code, lookup)
        out.append(row)
    return out
