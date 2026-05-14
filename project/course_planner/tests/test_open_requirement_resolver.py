"""Open Core / GE requirement resolution.

For Workday items that have no specific course code (e.g.
``"Core: ENGR: RTC 3"``, ``"Core: ENGR: Experiential Learning for Social
Justice"``), the planning agent normalizes the text and looks up
candidate courses in the schedule's Course-Tags reverse index.

These tests pin the normalize + lookup contract so a future tweak to one
side doesn't quietly break the other.
"""

from __future__ import annotations

import pytest

from agents.planning_agent import _normalize_open_req_text, _resolve_open_requirement


# ── _normalize_open_req_text ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Core: ENGR: RTC 3", "rtc 3"),
        ("Core: ENGR: ELSJ", "elsj"),
        ("Core: ENGR: Advanced Writing", "advanced writing"),
        ("Core: ENGR: Experiential Learning for Social Justice",
         "experiential learning for social justice"),
        # Strip parenthetical detail
        ("Core: ENGR: Arts (ENGL 181 & Design Project, OR 4 quarter units)",
         "arts"),
        # Other prefixes
        ("Core: CSE: Advanced Writing", "advanced writing"),
        ("Core: Religious Studies", "religious studies"),
        # No known prefix → keep as-is (lowercased, trimmed)
        ("Random label", "random label"),
        # Empty + whitespace
        ("", ""),
        ("   ", ""),
    ],
)
def test_normalize_open_req_text(raw, expected):
    assert _normalize_open_req_text(raw) == expected


def test_normalize_strips_only_leading_known_prefix():
    """The function should peel the first matching prefix off the front and
    stop — not recurse — so multiple ``"Core: "`` chains aren't collapsed."""
    out = _normalize_open_req_text("Core: ENGR: Core: ENGR: nested")
    # First matched prefix is "Core: ENGR: ", leaving "Core: ENGR: nested"
    # which gets lowercased.
    assert out == "core: engr: nested"


# ── _resolve_open_requirement ────────────────────────────────────────────────


def _slot():
    return {
        "instructors": [], "meeting_days": [],
        "meeting_start_min": None, "meeting_end_min": None,
    }


def test_resolve_exact_tag_match_returns_courses_in_schedule():
    cat = {"rtc 3": ["SCTR 128", "THEO 111", "THEO 99X"]}
    sched = {
        ("SCTR", "128"): _slot(),
        ("THEO", "111"): _slot(),
        # THEO 99X NOT in schedule next term
    }
    out = _resolve_open_requirement("Core: ENGR: RTC 3", cat, sched)
    assert "SCTR 128" in out
    assert "THEO 111" in out
    assert "THEO 99X" not in out, "must filter to courses actually in next-term schedule"


def test_resolve_returns_empty_for_unknown_requirement_text():
    cat = {"rtc 3": ["SCTR 128"]}
    sched = {("SCTR", "128"): _slot()}
    assert _resolve_open_requirement("This isn't a real category", cat, sched) == []


def test_resolve_falls_back_to_substring_match():
    """When there's no exact tag match, the resolver does a substring scan.

    ``"experiential learning for social justice"`` is the long-form
    description; a tag indexed under the short code ``elsj`` is matched
    by the substring fallback (``norm in key`` or ``key in norm``)."""
    cat = {
        "experiential learning for social justice": ["ANTH 3", "COMM 116"],
        "elsj": ["ANTH 3", "COMM 116"],
    }
    sched = {("ANTH", "3"): _slot(), ("COMM", "116"): _slot()}
    out = _resolve_open_requirement(
        "Core: ENGR: Experiential Learning for Social Justice", cat, sched
    )
    assert set(out) == {"ANTH 3", "COMM 116"}


def test_resolve_empty_inputs_safe():
    assert _resolve_open_requirement("", {}, {}) == []
    assert _resolve_open_requirement("Core: ENGR: RTC 3", {}, {}) == []
    assert _resolve_open_requirement("Core: ENGR: RTC 3", {"rtc 3": ["X 1"]}, {}) == []


def test_resolve_real_world_arts_requirement():
    """The student's Arts requirement is the full Workday phrasing.
    Parenthetical detail must be stripped before lookup."""
    cat = {"arts": ["ARTS 30", "ARTH 11A"]}
    sched = {("ARTS", "30"): _slot(), ("ARTH", "11A"): _slot()}
    out = _resolve_open_requirement(
        "Core: ENGR: Arts (ENGL 181 & Design Project, OR 4 quarter units from approved list)",
        cat, sched,
    )
    assert set(out) == {"ARTS 30", "ARTH 11A"}
