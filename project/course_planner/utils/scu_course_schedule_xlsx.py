"""
Parse SCU Find Course / Sections-style exports (.xlsx) to align recommended courses with
scheduled instructors AND real meeting days/times.

Default files (relative to the ``course_planner/`` package directory):
- ``SCU_Find_Course_Sections.xlsx``
- ``scu_find_course.xlsx``

Index entry shape:
  {
    "instructors": list[str],          # unique instructor names
    "meeting_days": list[int],         # 0=Mon … 4=Fri
    "meeting_start_min": int | None,   # minutes from 8:00 AM
    "meeting_end_min":   int | None,   # minutes from 8:00 AM
  }
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

_COURSE_PLANNER_DIR = Path(__file__).resolve().parents[1]
_DEFAULT_SCHEDULE_FILES = (
    _COURSE_PLANNER_DIR / "SCU_Find_Course_Sections.xlsx",
    _COURSE_PLANNER_DIR / "scu_find_course.xlsx",
)

_SCHEDULE_SUBJECT_TYPOS: dict[str, str] = {"CSEE": "CSEN"}

_CALENDAR_START_MIN = 8 * 60   # 8:00 AM
_CALENDAR_END_MIN   = 18 * 60  # 6:00 PM

# Day token → weekday index (0=Mon, 4=Fri)
_DAY_TOKEN_MAP: dict[str, int] = {
    "M": 0, "MON": 0, "MONDAY": 0,
    "T": 1, "TU": 1, "TUE": 1, "TUES": 1, "TUESDAY": 1,
    "W": 2, "WED": 2, "WEDNESDAY": 2,
    "TH": 3, "THU": 3, "THUR": 3, "THURS": 3, "THURSDAY": 3, "R": 3,
    "F": 4, "FRI": 4, "FRIDAY": 4,
}

# Candidate column header names (lower-cased for matching)
_DAYS_HEADERS   = {"days", "day", "meeting days", "meeting day", "mtg days", "mtg day"}
_START_HEADERS  = {"mtg start", "meeting start", "start time", "start", "begin time", "begin"}
_END_HEADERS    = {"mtg end", "meeting end", "end time", "end"}
_TIMES_HEADERS  = {"times", "meeting times", "time", "meeting time", "mtg time", "meeting patterns", "meeting pattern", "mtg patterns", "patterns"}


# ── helpers ─────────────────────────────────────────────────────────────────

def expand_subjects_for_schedule_lookup(subject_tokens: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in subject_tokens:
        u = raw.strip().upper()
        if not u:
            continue
        for cand in (u, _SCHEDULE_SUBJECT_TYPOS.get(u, "")):
            if cand and cand not in seen:
                out.append(cand)
                seen.add(cand)
    return out


def _find_schedule_path(explicit: Path | None) -> Path | None:
    if explicit is not None and explicit.is_file():
        return explicit
    for p in _DEFAULT_SCHEDULE_FILES:
        if p.is_file():
            return p
    return None


def _parse_section_subject_number(course_section: str | None) -> tuple[str, str] | None:
    if not course_section or not isinstance(course_section, str):
        return None
    head = course_section.split(" - ")[0].strip().upper()
    m = re.match(r"^([A-Z]{2,8})\s+(\d+[A-Z]?)\s*-\s*\d+\s*$", head)
    if not m:
        return None
    return m.group(1), m.group(2)


def _parse_days(cell: Any) -> list[int]:
    """'M W F' or 'MWF' or 'M,W,F' → [0, 2, 4]."""
    if cell is None:
        return []
    text = str(cell).upper().strip()
    # Remove anything after "|" (in case days+times are in one cell, e.g. "M W F | 9:15 AM")
    text = text.split("|")[0].strip()
    # Normalise separators
    text = text.replace(",", " ").replace("/", " ")
    # Handle compact "MWF" / "MW" without spaces by inserting spaces between known tokens
    # (longest first to avoid "TH" being consumed as "T" + "H")
    expanded = re.sub(r"\b(TH|MON|TUE|TUES|WED|THU|THUR|THURS|FRI|TU)\b", r" \1 ", text, flags=re.I)
    expanded = re.sub(r"\b([MTWRF])\b", r" \1 ", expanded)
    days: list[int] = []
    for tok in expanded.split():
        idx = _DAY_TOKEN_MAP.get(tok.upper())
        if idx is not None and idx not in days:
            days.append(idx)
    return sorted(days)


def _parse_single_time(s: str) -> int | None:
    """'9:15 AM' → minutes from midnight."""
    m = re.fullmatch(r"(\d{1,2}):(\d{2})\s*(AM|PM)?", s.strip(), re.IGNORECASE)
    if not m:
        return None
    h, mn = int(m.group(1)), int(m.group(2))
    ampm = (m.group(3) or "").upper()
    if ampm == "PM" and h != 12:
        h += 12
    elif ampm == "AM" and h == 12:
        h = 0
    return h * 60 + mn


def _offset(total_min: int) -> int:
    """Minutes-from-midnight → minutes-from-8AM, clamped to calendar range."""
    return max(0, min(_CALENDAR_END_MIN - _CALENDAR_START_MIN, total_min - _CALENDAR_START_MIN))


def _parse_time_range(cell: Any) -> tuple[int, int] | None:
    """'9:15 AM - 10:20 AM' → (start_offset, end_offset) in minutes from 8 AM."""
    if cell is None:
        return None
    text = str(cell).strip()
    # Strip leading days portion if combined: "M W F | 9:15 AM - 10:20 AM"
    if "|" in text:
        text = text.split("|", 1)[1].strip()
    m = re.search(
        r"(\d{1,2}:\d{2}\s*(?:AM|PM)?)\s*[-–]\s*(\d{1,2}:\d{2}\s*(?:AM|PM)?)",
        text,
        re.IGNORECASE,
    )
    if not m:
        return None
    s = _parse_single_time(m.group(1))
    e = _parse_single_time(m.group(2))
    if s is None or e is None:
        return None
    # If PM marker absent on start, inherit from end when end > 12:00 noon
    if e >= 12 * 60 and s < 12 * 60 and "pm" not in m.group(1).lower() and "am" not in m.group(1).lower():
        # Both times likely PM (e.g. "1:00 - 2:00 PM")
        pass  # leave as-is; single-time parser already handles explicit AM/PM
    start_off = _offset(s)
    end_off   = _offset(e)
    if start_off >= end_off:
        return None
    return start_off, end_off


def _normalize_planner_course_text(course_code: str) -> str:
    u = course_code.upper().replace("&", " ").replace(",", " ")
    u = re.sub(r"(\d+)\s*/\s*L\b", r"\1L", u)
    u = u.replace("/", " ")
    return " ".join(u.split())


def planned_section_keys(course_code: str) -> set[tuple[str, str]]:
    text = _normalize_planner_course_text(course_code)
    tokens = [t for t in text.split() if t]
    keys: set[tuple[str, str]] = set()
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if (
            i + 1 < len(tokens)
            and re.fullmatch(r"[A-Z]{2,8}", t)
            and re.fullmatch(r"\d+[A-Z]?", tokens[i + 1])
        ):
            subj, num = t, tokens[i + 1]
            keys.add((subj, num))
            typo = _SCHEDULE_SUBJECT_TYPOS.get(subj)
            if typo:
                keys.add((typo, num))
                subj = typo
            if subj == "COEN":
                keys.add(("CSEN", num))
            elif subj == "CSEN":
                keys.add(("COEN", num))
            elif subj == "ECEN":
                keys.add(("ELEN", num))
            elif subj == "ELEN":
                keys.add(("ECEN", num))
            i += 2
            continue
        i += 1
    return keys


def _split_instructor_aliases(cell: Any) -> list[str]:
    if not cell or not isinstance(cell, str):
        return []
    return [p.strip() for p in re.split(r"\|", cell) if p.strip() and p.strip().lower() != "none"]


def _find_col(header: list[str], candidates: set[str]) -> int | None:
    for i, h in enumerate(header):
        if h.strip().lower() in candidates:
            return i
    return None


def load_schedule_section_index(path: Path | None = None) -> dict[tuple[str, str], dict[str, Any]]:
    """
    Read xlsx and build (subject, catalog_number) -> entry dict:
      {instructors, meeting_days, meeting_start_min, meeting_end_min}
    """
    p = _find_schedule_path(path)
    if p is None:
        return {}

    index: dict[tuple[str, str], dict[str, Any]] = {}
    wb = load_workbook(p, read_only=True, data_only=True)
    try:
        ws = wb.active
        it = ws.iter_rows(values_only=True)
        header_row = next(it, None)
        if not header_row:
            return {}
        h = [str(c).strip() if c is not None else "" for c in header_row]

        # Required columns
        try:
            idx_sec = h.index("Course Section")
        except ValueError:
            return {}
        idx_inst = next((i for i, x in enumerate(h) if x == "All Instructors"), None)

        # Optional time columns
        idx_days  = _find_col(h, _DAYS_HEADERS)
        idx_start = _find_col(h, _START_HEADERS)
        idx_end   = _find_col(h, _END_HEADERS)
        idx_times = _find_col(h, _TIMES_HEADERS)  # combined "9:15 AM - 10:20 AM"

        def _get(row: tuple, idx: int | None) -> Any:
            if idx is None or idx >= len(row):
                return None
            return row[idx]

        for row in it:
            if not row or idx_sec >= len(row):
                continue
            key = _parse_section_subject_number(row[idx_sec])
            if not key:
                continue

            names = _split_instructor_aliases(_get(row, idx_inst)) if idx_inst is not None else []

            # Parse meeting days
            days: list[int] = []
            raw_days = _get(row, idx_days)
            if raw_days:
                days = _parse_days(raw_days)
            elif idx_times is not None:
                # Combined cell may contain "M W F | 9:15 AM - 10:20 AM"
                days = _parse_days(_get(row, idx_times))

            # Parse meeting times
            time_range: tuple[int, int] | None = None
            if idx_start is not None and idx_end is not None:
                raw_s = _get(row, idx_start)
                raw_e = _get(row, idx_end)
                if raw_s and raw_e:
                    s = _parse_single_time(str(raw_s))
                    e = _parse_single_time(str(raw_e))
                    if s is not None and e is not None:
                        off_s = _offset(s)
                        off_e = _offset(e)
                        if off_s < off_e:
                            time_range = (off_s, off_e)
            if time_range is None and idx_times is not None:
                time_range = _parse_time_range(_get(row, idx_times))
            if time_range is None and idx_days is None and idx_times is not None:
                # fallback: try combined days+times cell
                time_range = _parse_time_range(_get(row, idx_times))

            entry = index.setdefault(
                key,
                {"instructors": [], "meeting_days": [], "meeting_start_min": None, "meeting_end_min": None},
            )
            for n in names:
                if n not in entry["instructors"]:
                    entry["instructors"].append(n)
            if days and not entry["meeting_days"]:
                entry["meeting_days"] = days
            if time_range and entry["meeting_start_min"] is None:
                entry["meeting_start_min"] = time_range[0]
                entry["meeting_end_min"] = time_range[1]

    finally:
        wb.close()

    _merge_lab_instructors_into_base(index)
    _mirror_ecen_elen_keys(index)
    return index


def _merge_lab_instructors_into_base(index: dict[tuple[str, str], dict[str, Any]]) -> None:
    for (subj, num) in list(index.keys()):
        s = str(num)
        if not s.endswith("L") or len(s) < 2 or not s[:-1].isdigit():
            continue
        base_key = (subj, s[:-1])
        base = index.setdefault(base_key, {"instructors": [], "meeting_days": [], "meeting_start_min": None, "meeting_end_min": None})
        for n in index.get((subj, s), {}).get("instructors", []):
            if n not in base["instructors"]:
                base["instructors"].append(n)


def _mirror_ecen_elen_keys(index: dict[tuple[str, str], dict[str, Any]]) -> None:
    for (subj, num) in list(index.keys()):
        if subj == "ECEN":
            alt = ("ELEN", num)
            if alt not in index:
                index[alt] = index[(subj, num)]
        elif subj == "ELEN":
            alt = ("ECEN", num)
            if alt not in index:
                index[alt] = index[(subj, num)]


def scheduled_instructors_for_course(
    course_code: str, index: dict[tuple[str, str], dict[str, Any]]
) -> list[str]:
    if not index:
        return []
    want = planned_section_keys(course_code)
    out: list[str] = []
    for k in want:
        entry = index.get(k)
        if entry:
            for name in entry.get("instructors", []):
                if name not in out:
                    out.append(name)
    return out


def meeting_times_for_course(
    course_code: str, index: dict[tuple[str, str], dict[str, Any]]
) -> dict[str, Any] | None:
    """Return {meeting_days, meeting_start_min, meeting_end_min} or None if not found."""
    if not index:
        return None
    for k in planned_section_keys(course_code):
        entry = index.get(k)
        if entry and entry.get("meeting_days") and entry.get("meeting_start_min") is not None:
            return {
                "meeting_days": entry["meeting_days"],
                "meeting_start_min": entry["meeting_start_min"],
                "meeting_end_min": entry["meeting_end_min"],
            }
    return None
