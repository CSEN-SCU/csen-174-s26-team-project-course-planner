"""Helpers for academic progress rows → planner inputs."""

from __future__ import annotations

import re
from typing import Any

from utils.scu_course_schedule_xlsx import planned_section_keys

_COURSE_CODE_RE = re.compile(r"^([A-Z]{2,6})\s+(\d{1,3}[A-Z]?)$", re.IGNORECASE)

# Prose tokens that match ``{2,6}`` uppercase words but are not course subjects.
_NON_SUBJECT_TOKENS = frozenset(
    {
        "AND",
        "OR",
        "THE",
        "FOR",
        "MAJOR",
        "CORE",
        "UNIV",
        "UNIVERSITY",
        "COMPUTER",
        "SCIENCE",
        "ENGINEERING",
    }
)
# Core requirement tags that look like SUBJ NUM but are not catalog courses.
_OPEN_TAG_SUBJECTS = frozenset({"RTC", "ELSJ"})

_COMPLETED_STATUSES = frozenset({"satisfied", "in progress"})

_DEFAULT_LECTURE_UNITS = 4
_DEFAULT_LAB_UNITS = 1


def _normalize_code(code: str | None) -> str:
    return (code or "").strip().upper()


def extract_codes_from_requirement(text: str) -> list[str]:
    """Extract course codes embedded in a Workday requirement description.

    Handles SCU patterns like ``CSEN/COEN 122 & 122L`` and ``CSEN/COEN 194/L``.
    """
    t = (text or "").upper()
    t = re.sub(r"(\d+[A-Z]?)/L\b", r"\1 & \1L", t)

    slash_subj_re = re.compile(r"\b([A-Z]{2,6}(?:/[A-Z]{2,6})+)\b")
    subj_group_positions: list[tuple[int, int, list[str]]] = []
    for m in slash_subj_re.finditer(t):
        variants = m.group(0).split("/")
        subj_group_positions.append((m.start(), m.end(), variants))

    num_re = re.compile(r"\b(\d{1,3}[A-Z]?)\b")

    codes: list[str] = []
    seen: set[str] = set()

    for _start, end, variants in subj_group_positions:
        tail = t[end : end + 80]
        nums = num_re.findall(tail)
        for num in nums[:4]:
            for subj in variants:
                if subj in _NON_SUBJECT_TOKENS:
                    continue
                c = f"{subj} {num}"
                if c not in seen:
                    codes.append(c)
                    seen.add(c)

    if not codes:
        simple_re = re.compile(r"\b([A-Z]{2,6})\s+(\d{1,3}[A-Z]?)\b")
        for subj, num in simple_re.findall(t):
            if subj in _NON_SUBJECT_TOKENS:
                continue
            c = f"{subj} {num}"
            if c not in seen:
                codes.append(c)
                seen.add(c)

    return codes


def _is_catalog_course_code(code: str) -> bool:
    parts = _normalize_code(code).split()
    if len(parts) != 2:
        return False
    subj, _num = parts
    return subj not in _NON_SUBJECT_TOKENS and subj not in _OPEN_TAG_SUBJECTS


def _primary_hint_from_extracted(codes: list[str]) -> str | None:
    """Pick one hint code for ``missing_details[i].course`` (first lecture)."""
    for c in codes:
        parts = c.split()
        if len(parts) != 2:
            continue
        _subj, num = parts
        if num.endswith("L") and len(num) > 1:
            continue
        if _is_catalog_course_code(c):
            return c
    return None


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
        for c in extract_codes_from_requirement(req):
            lookup[_normalize_code(c)] = max(lookup.get(_normalize_code(c), 0), units)

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
        extracted = extract_codes_from_requirement(rq) if rq else []
        if extracted:
            row["course"] = _primary_hint_from_extracted(extracted)
        code = _normalize_code(row.get("course"))
        if code and not _parse_units(row.get("units")):
            row["units"] = default_units_for_code(code, lookup)
        out.append(row)
    return out
