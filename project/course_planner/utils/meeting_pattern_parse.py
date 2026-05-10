"""Parse SCU-style Meeting Patterns strings (days + bar + time range).

Single source of truth for calendar placement and time captions; keeps behavior
testable without importing the Streamlit entrypoint.
"""

from __future__ import annotations

import re
from typing import Optional

# Matches "9:00 AM", "11:45am", "12:05 PM" in free text (hyphens may appear elsewhere).
_TIME_TOKEN_RE = re.compile(r"\d{1,2}:\d{2}\s*(?:[AaPp][Mm])", re.I)


def _tokenize_days(days_part: str) -> list[str]:
    """Split day letters, treating ``Th`` before a bare ``T`` so ``TTh`` → Tue + Thu."""
    s = days_part.replace(",", " ").strip()
    if not s:
        return []
    tokens: list[str] = []
    i = 0
    n = len(s)
    while i < n:
        if s[i].isspace():
            i += 1
            continue
        if i + 1 < n and s[i : i + 2].lower() == "th":
            tokens.append("Th")
            i += 2
            continue
        ch = s[i]
        if ch.upper() in "MTWRF":
            tokens.append(ch.upper())
        i += 1
    return tokens


def parse_schedule(schedule_str: str) -> Optional[dict]:
    """
    Input: ``M W F | 11:45 AM - 12:50 PM`` or ``MWRF|9:00 AM--10:15 AM`` or ``TR|10:00 AM - 11:00 AM``.
    Output: ``{"days": [...], "start": "...", "end": "..."}`` or None.
    """
    if not schedule_str or "|" not in schedule_str:
        return None
    days_part, time_part = schedule_str.split("|", 1)
    days = _tokenize_days(days_part)
    if not days:
        return None

    t_raw = time_part.strip()
    times = _TIME_TOKEN_RE.findall(t_raw)
    if len(times) >= 2:
        start, end = times[0].strip(), times[-1].strip()
    else:
        parts = [p.strip() for p in t_raw.split("-") if p.strip()]
        if len(parts) < 2:
            return None
        start, end = parts[0], parts[-1]

    return {"days": days, "start": start, "end": end}
