"""Open Core / GE requirement resolution.

For Academic Progress export items that have no specific course code (e.g.
``"Core: ENGR: RTC 3"``, ``"Core: ENGR: Experiential Learning for Social
Justice"``), the planning agent normalizes the text and looks up
candidate courses in the schedule's Course-Tags reverse index.

These tests pin the normalize + lookup contract so a future tweak to one
side doesn't quietly break the other.

R4 additions: Educational Enrichment scoping, rating sort, top-5 cap.
"""

from __future__ import annotations

import pytest

from agents.planning_agent import (
    _normalize_open_req_text,
    _resolve_open_requirement,
    _best_candidate_rating,
    _OPEN_REQ_CANDIDATE_LIMIT,
)


# ── _normalize_open_req_text ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Core: ENGR: RTC 3", "rtc 3"),
        ("Core: ENGR: ELSJ", "elsj"),
        ("Core: ENGR: Advanced Writing", "advanced writing"),
        ("Core: ENGR: Experiential Learning for Social Justice",
         "experiential learning for social justice"),
        # Ampersand must be spelled out to match the category-index keys
        # (which use "and"), otherwise the Workday "IDEAS N" placeholder leaks
        # through instead of a real Cultures & Ideas course.
        ("Core: ENGR: Cultures & Ideas 1", "cultures and ideas 1"),
        ("Core: ENGR: Critical Thinking & Writing 2",
         "critical thinking and writing 2"),
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


def test_resolve_cultures_and_ideas_matches_ampersand_requirement():
    """Regression: 'Cultures & Ideas 1' must hit the 'cultures and ideas 1' tag.

    Before the &→and fix this returned [], so the Workday placeholder code
    ('IDEAS 1') leaked into the four-year plan as a fake course.
    """
    cat = {"cultures and ideas 1": ["ANTH 11A", "HIST 11A"]}
    sched = {("ANTH", "11A"): _slot(), ("HIST", "11A"): _slot()}
    out = _resolve_open_requirement("Core: ENGR: Cultures & Ideas 1", cat, sched)
    assert set(out) == {"ANTH 11A", "HIST 11A"}


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
    """The student's Arts requirement is the full Academic Progress export phrasing.
    Parenthetical detail must be stripped before lookup."""
    cat = {"arts": ["ARTS 30", "ARTH 11A"]}
    sched = {("ARTS", "30"): _slot(), ("ARTH", "11A"): _slot()}
    out = _resolve_open_requirement(
        "Core: ENGR: Arts (ENGL 181 & Design Project, OR 4 quarter units from approved list)",
        cat, sched,
    )
    assert set(out) == {"ARTS 30", "ARTH 11A"}


# ── R4: Educational Enrichment scoping ───────────────────────────────────────


def _rated_slot(rating: float) -> dict:
    """Schedule slot whose sole instructor has a known rating (via ratings dict)."""
    return {
        "instructors": [f"Prof_{rating}"],
        "meeting_days": [],
        "meeting_start_min": None,
        "meeting_end_min": None,
    }


def test_resolve_educational_enrichment_restricts_to_core_integrations(monkeypatch):
    """Educational Enrichment must exclude courses not in the Core Integrations set."""
    # Monkeypatch the xlsx-backed set to a controlled frozenset
    import agents.planning_agent as pa
    monkeypatch.setattr(pa, "load_core_integrations_course_set", lambda: frozenset({"ETHN 50", "COMM 30"}))
    monkeypatch.setattr(pa, "load_instructor_ratings", lambda: {})

    # Category index has three matches; only two are Core Integrations tagged
    cat = {"educational enrichment": ["ETHN 50", "COMM 30", "POLS 1"]}
    sched = {
        ("ETHN", "50"): _slot(),
        ("COMM", "30"): _slot(),
        ("POLS", "1"): _slot(),  # NOT in core_integrations set → must be excluded
    }
    out = _resolve_open_requirement(
        "Computer Science and Engineering Major: Educational Enrichment – Courses",
        cat, sched,
    )
    assert "POLS 1" not in out, "non-Core-Integrations course must be excluded"
    assert "ETHN 50" in out
    assert "COMM 30" in out


def test_resolve_educational_enrichment_empty_integrations_set_does_not_filter(monkeypatch):
    """When the xlsx is absent (empty integrations set), fall back gracefully —
    no filter applied so students still get candidates."""
    import agents.planning_agent as pa
    monkeypatch.setattr(pa, "load_core_integrations_course_set", lambda: frozenset())
    monkeypatch.setattr(pa, "load_instructor_ratings", lambda: {})

    cat = {"educational enrichment": ["ETHN 50", "POLS 1"]}
    sched = {("ETHN", "50"): _slot(), ("POLS", "1"): _slot()}
    out = _resolve_open_requirement(
        "Educational Enrichment – Courses", cat, sched
    )
    assert "ETHN 50" in out
    assert "POLS 1" in out


# ── R4: rating sort ───────────────────────────────────────────────────────────


def test_resolve_sorts_candidates_by_rating_descending(monkeypatch):
    """Candidates must be ordered best-rated first."""
    import agents.planning_agent as pa
    monkeypatch.setattr(pa, "load_core_integrations_course_set", lambda: frozenset())

    ratings = {
        "Prof_4.8": {"rating": 4.8},
        "Prof_3.1": {"rating": 3.1},
        "Prof_2.0": {"rating": 2.0},
    }
    monkeypatch.setattr(pa, "load_instructor_ratings", lambda: ratings)

    cat = {"rtc 3": ["THEO 50", "SCTR 20", "ANTH 60"]}
    sched = {
        ("THEO", "50"): _rated_slot(3.1),
        ("SCTR", "20"): _rated_slot(4.8),
        ("ANTH", "60"): _rated_slot(2.0),
    }
    out = _resolve_open_requirement("Core: ENGR: RTC 3", cat, sched)
    assert out[0] == "SCTR 20", "highest-rated course must come first"
    assert out[1] == "THEO 50"
    assert out[2] == "ANTH 60"


def test_resolve_unrated_courses_sort_last(monkeypatch):
    """Courses with no rating data sort below rated courses."""
    import agents.planning_agent as pa
    monkeypatch.setattr(pa, "load_core_integrations_course_set", lambda: frozenset())
    monkeypatch.setattr(pa, "load_instructor_ratings", lambda: {"Prof_4.0": {"rating": 4.0}})

    cat = {"elsj": ["ANTH 3", "COMM 116"]}
    sched = {
        ("ANTH", "3"): _slot(),           # no rating data (instructors=[])
        ("COMM", "116"): _rated_slot(4.0),
    }
    out = _resolve_open_requirement("Core: ENGR: ELSJ", cat, sched)
    assert out[0] == "COMM 116", "rated course must precede unrated"
    assert out[1] == "ANTH 3"


# ── R4: top-5 cap ────────────────────────────────────────────────────────────


def test_resolve_caps_candidates_at_limit(monkeypatch):
    """At most _OPEN_REQ_CANDIDATE_LIMIT courses are returned."""
    import agents.planning_agent as pa
    monkeypatch.setattr(pa, "load_core_integrations_course_set", lambda: frozenset())
    monkeypatch.setattr(pa, "load_instructor_ratings", lambda: {})

    # Build 10 distinct candidates
    courses = [f"DEPT {i}" for i in range(10)]
    cat = {"arts": courses}
    sched = {("DEPT", str(i)): _slot() for i in range(10)}
    out = _resolve_open_requirement("Core: ENGR: Arts", cat, sched)
    assert len(out) <= _OPEN_REQ_CANDIDATE_LIMIT


# ── _best_candidate_rating ────────────────────────────────────────────────────


def test_best_candidate_rating_returns_max_across_sections():
    ratings = {"Alice": {"rating": 3.5}, "Bob": {"rating": 4.9}}
    sched = {
        ("CSEN", "50"): {"instructors": ["Alice"], "meeting_days": [], "meeting_start_min": None, "meeting_end_min": None},
        ("COEN", "50"): {"instructors": ["Bob"], "meeting_days": [], "meeting_start_min": None, "meeting_end_min": None},
    }
    assert _best_candidate_rating("CSEN 50", sched, ratings) == 4.9


def test_best_candidate_rating_returns_negative_when_no_data():
    assert _best_candidate_rating("CSEN 999", {}, {}) == -1.0
