"""Parse natural-language schedule preferences and score section options.

Used by the deterministic schedule selector, LLM planner post-processing,
and (indirectly) the calendar via backend-stamped section choices.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

# Calendar grid uses minutes from 8:00 AM.
_CALENDAR_BASE_HOUR = 8

_NO_MORNING_RE = re.compile(
    r"no\s+(?:early|morning)|after\s+10|after\s+9|nothing\s+(?:early|before)",
    re.IGNORECASE,
)
_PREFER_AFTERNOON_RE = re.compile(
    r"prefer\s+afternoon|afternoon\s+(?:classes|only)",
    re.IGNORECASE,
)
_LIGHT_LOAD_RE = re.compile(r"light\s+(?:load|quarter)|easy\s+quarter", re.IGNORECASE)
_AVOID_VERB_RE = re.compile(
    r"\b(?:no|not|don't|do\s+not|avoid|without|skip|minimize|minimise)\b",
    re.IGNORECASE,
)
_TIME_RE = re.compile(r"(\d{1,2}):(\d{2})\s*(am|pm)?", re.IGNORECASE)
_MWF_RE = re.compile(r"\bMWF\b|\bM\s+W\s+F\b", re.IGNORECASE)
_MTWRF_RE = re.compile(r"\bMTWRF\b|\bM\s*T\s*W\s*Th?\s*F\b", re.IGNORECASE)
_TTH_RE = re.compile(r"\bT\s*Th\b|\bTTh\b|\bT/Th\b", re.IGNORECASE)

_DAY_TOKEN_RE = re.compile(
    r"\b(?:Mon(?:day)?|Tue(?:s(?:day)?)?|Wed(?:nesday)?|Thu(?:rs(?:day)?)?|Fri(?:day)?|"
    r"M(?:\s|$)|T(?:\s|$)|W(?:\s|$)|Th(?:\s|$)|F(?:\s|$))\b",
    re.IGNORECASE,
)

_EXPLICIT_AVOID_RE = re.compile(
    r"(?:no|don't|do\s+not|avoid|not\s+want|without|skip)\s+(?:a\s+)?"
    r"(?:(?:MWF|MTWRF|M\s*W\s*F|M\s*T\s*W\s*(?:Th|R)?\s*F|T\s*Th|TTh|[MTWThF\s]+)\s+)?"
    r"(?:class(?:es)?\s+)?(?:at\s+)?(\d{1,2}):(\d{2})\s*(am|pm)?",
    re.IGNORECASE,
)

_AVOIDANCE_PENALTY = 10.0
_TIME_MATCH_TOLERANCE_MIN = 20


@dataclass(frozen=True)
class SlotAvoidance:
    """A day/time window the student asked to avoid."""

    days: frozenset[int] | None  # None = any weekday
    start_min: int
    end_min: int


def clock_to_calendar_offset(hour: int, minute: int, ampm: str | None) -> int:
    """Convert clock time to minutes-from-8AM offset used in the schedule index."""
    h = int(hour)
    m = int(minute)
    if ampm:
        am = ampm.lower().startswith("a")
        if h == 12:
            h = 0 if am else 12
        elif not am:
            h += 12
    return (h - _CALENDAR_BASE_HOUR) * 60 + m


def _parse_day_token(token: str) -> int | None:
    t = token.strip().upper()
    if t in ("M", "MON", "MONDAY"):
        return 0
    if t in ("T", "TUE", "TUES", "TUESDAY"):
        return 1
    if t in ("W", "WED", "WEDNESDAY"):
        return 2
    if t in ("TH", "THU", "THUR", "THURS", "THURSDAY", "R"):
        return 3
    if t in ("F", "FRI", "FRIDAY"):
        return 4
    return None


def _days_from_text(fragment: str) -> frozenset[int] | None:
    if not fragment or not fragment.strip():
        return None
    upper = fragment.upper()
    if _MWF_RE.search(fragment):
        return frozenset({0, 2, 4})
    if _MTWRF_RE.search(fragment):
        return frozenset({0, 1, 2, 3, 4})
    if _TTH_RE.search(fragment):
        return frozenset({1, 3})
    days: set[int] = set()
    for m in _DAY_TOKEN_RE.finditer(fragment):
        d = _parse_day_token(m.group(0))
        if d is not None:
            days.add(d)
    return frozenset(days) if days else None


def parse_slot_avoidances(text: str) -> list[SlotAvoidance]:
    """Extract explicit day/time slots the student wants to avoid."""
    if not text or not _AVOID_VERB_RE.search(text):
        return []

    avoidances: list[SlotAvoidance] = []
    seen: set[tuple[frozenset[int] | None, int, int]] = set()

    for m in _EXPLICIT_AVOID_RE.finditer(text):
        days = _days_from_text(m.group(0))
        h, mi, ampm = int(m.group(1)), int(m.group(2)), m.group(3)
        center = clock_to_calendar_offset(h, mi, ampm)
        start = center - _TIME_MATCH_TOLERANCE_MIN
        end = center + _TIME_MATCH_TOLERANCE_MIN
        key = (days, start, end)
        if key not in seen:
            seen.add(key)
            avoidances.append(SlotAvoidance(days=days, start_min=start, end_min=end))

    # Fallback: "no 10:30" / "avoid MWF" with time elsewhere in the message.
    if not avoidances and _AVOID_VERB_RE.search(text):
        days = _days_from_text(text)
        for tm in _TIME_RE.finditer(text):
            h, mi, ampm = int(tm.group(1)), int(tm.group(2)), tm.group(3)
            center = clock_to_calendar_offset(h, mi, ampm)
            start = center - _TIME_MATCH_TOLERANCE_MIN
            end = center + _TIME_MATCH_TOLERANCE_MIN
            key = (days, start, end)
            if key not in seen:
                seen.add(key)
                avoidances.append(SlotAvoidance(days=days, start_min=start, end_min=end))

    return avoidances


def has_explicit_schedule_avoidances(text: str) -> bool:
    return bool(parse_slot_avoidances(text))


def _section_days(section: Any) -> set[int]:
    days = getattr(section, "meeting_days", None)
    if days is None and isinstance(section, dict):
        days = section.get("meeting_days")
    return set(days or [])


def _section_start(section: Any) -> int | None:
    start = getattr(section, "meeting_start_min", None)
    if start is None and isinstance(section, dict):
        start = section.get("meeting_start_min")
    return int(start) if start is not None else None


def _section_end(section: Any) -> int | None:
    end = getattr(section, "meeting_end_min", None)
    if end is None and isinstance(section, dict):
        end = section.get("meeting_end_min")
    return int(end) if end is not None else None


def section_matches_avoidance(section: Any, avoidance: SlotAvoidance) -> bool:
    start = _section_start(section)
    if start is None:
        return False
    days = _section_days(section)
    if avoidance.days is not None:
        if not (days & set(avoidance.days)):
            return False
    return avoidance.start_min <= start <= avoidance.end_min


def preference_score_for_section(section: Any, pref: str) -> float:
    """Higher is better. Large penalties for explicitly avoided slots."""
    score = 0.0
    start = _section_start(section)
    if start is None:
        return score

    for av in parse_slot_avoidances(pref):
        if section_matches_avoidance(section, av):
            score -= _AVOIDANCE_PENALTY

    if _NO_MORNING_RE.search(pref) and start < 60:
        score -= 1.0
    if _PREFER_AFTERNOON_RE.search(pref) and start < 240:
        score -= 0.5

    diff = getattr(section, "instructor_difficulty", None)
    if diff is None and isinstance(section, dict):
        diff = section.get("instructor_difficulty")
    if _LIGHT_LOAD_RE.search(pref) and diff is not None and diff > 3.5:
        score -= 0.5

    return score


def _section_rating(section: Any) -> float:
    rating = getattr(section, "instructor_rating", None)
    if rating is None and isinstance(section, dict):
        rating = section.get("instructor_rating")
    try:
        return float(rating) if rating is not None else -1.0
    except (TypeError, ValueError):
        return -1.0


def _section_difficulty(section: Any) -> float:
    diff = getattr(section, "instructor_difficulty", None)
    if diff is None and isinstance(section, dict):
        diff = section.get("instructor_difficulty")
    try:
        return float(diff) if diff is not None else 5.0
    except (TypeError, ValueError):
        return 5.0


def _section_number(section: Any) -> int:
    num = getattr(section, "section_number", None)
    if num is None and isinstance(section, dict):
        num = section.get("section")
    try:
        return int(num or 0)
    except (TypeError, ValueError):
        return 0


def rank_sections_for_preference(
    sections: Iterable[Any],
    user_preference: str,
) -> list[Any]:
    """Sort sections best-first for the student's schedule preferences."""
    return sorted(
        list(sections),
        key=lambda s: (
            preference_score_for_section(s, user_preference),
            _section_rating(s),
            -_section_difficulty(s),
            -_section_number(s),
        ),
        reverse=True,
    )


def pick_best_section_dict(
    sections: list[dict[str, Any]],
    user_preference: str,
    *,
    conflict_with: Iterable[Any] | None = None,
) -> dict[str, Any] | None:
    """Pick the best section row from ``all_sections_for_course`` output."""
    if not sections:
        return None

    def _section_conflict(a: Any, b: Any) -> bool:
        if (
            a.meeting_start_min is None
            or b.meeting_start_min is None
            or a.meeting_end_min is None
            or b.meeting_end_min is None
        ):
            return False
        shared = set(a.meeting_days) & set(b.meeting_days)
        if not shared:
            return False
        return a.meeting_start_min < b.meeting_end_min and b.meeting_start_min < a.meeting_end_min

    def _conflicts(sec: dict[str, Any]) -> bool:
        if not conflict_with:
            return False

        class _Wrap:
            def __init__(self, d: dict[str, Any]):
                self.meeting_days = tuple(d.get("meeting_days") or [])
                self.meeting_start_min = d.get("meeting_start_min")
                self.meeting_end_min = d.get("meeting_end_min")

        w = _Wrap(sec)
        for other in conflict_with:
            if _section_conflict(w, other):
                return True
        return False

    for sec in rank_sections_for_preference(sections, user_preference):
        if not _conflicts(sec):
            return sec
    return rank_sections_for_preference(sections, user_preference)[0]
