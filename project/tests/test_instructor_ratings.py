"""R5 — instructor ratings loader + best-section picker.

Pins the data pipeline (CSV → loader → tool → picker) so the
InstructorSelector node in the multi-agent graph chooses the
highest-rated section and degrades gracefully when rating data is
missing.
"""

from __future__ import annotations

import textwrap

import pytest

from utils import scu_course_schedule_xlsx as sx
from agents.multi_agent import graph as graph_mod


# ── Loader ───────────────────────────────────────────────────────────────────


def _write_ratings(tmp_path, body: str):
    p = tmp_path / "instructor_ratings.csv"
    p.write_text(textwrap.dedent(body), encoding="utf-8")
    return str(p)


def test_loader_parses_rows_and_skips_comments(tmp_path):
    csv_path = _write_ratings(
        tmp_path,
        """\
        # this is a comment header
        # another comment
        instructor_name,rating,difficulty,would_take_again_pct,source
        Jane Doe,4.5,2.1,90,seed_placeholder
        John Roe,3.2,3.8,55,seed_placeholder
        """,
    )
    sx.load_instructor_ratings.cache_clear()
    idx = sx.load_instructor_ratings(csv_path)
    assert idx["Jane Doe"]["rating"] == 4.5
    assert idx["Jane Doe"]["difficulty"] == 2.1
    assert idx["John Roe"]["would_take_again_pct"] == 55.0
    # case-insensitive lookup key present
    assert idx["jane doe"]["rating"] == 4.5


def test_loader_missing_file_returns_empty(tmp_path):
    sx.load_instructor_ratings.cache_clear()
    assert sx.load_instructor_ratings(str(tmp_path / "nope.csv")) == {}


def test_loader_handles_blank_and_bad_rating(tmp_path):
    csv_path = _write_ratings(
        tmp_path,
        """\
        instructor_name,rating,difficulty,would_take_again_pct,source
        No Rating,,,,manual
        Bad Rating,not_a_number,x,y,manual
        """,
    )
    sx.load_instructor_ratings.cache_clear()
    idx = sx.load_instructor_ratings(csv_path)
    assert idx["No Rating"]["rating"] is None
    assert idx["Bad Rating"]["rating"] is None  # unparseable → None, no crash


def test_instructor_rating_for_unknown_is_unavailable(tmp_path):
    csv_path = _write_ratings(
        tmp_path,
        """\
        instructor_name,rating,difficulty,would_take_again_pct,source
        Known Prof,4.0,3.0,80,manual
        """,
    )
    sx.load_instructor_ratings.cache_clear()
    idx = sx.load_instructor_ratings(csv_path)
    rec = sx.instructor_rating_for("Nobody", idx)
    assert rec["rating"] is None
    assert rec["source"] == "unavailable"


def test_shipped_csv_loads_and_is_placeholder_marked():
    """The checked-in seed CSV must load and be honestly tagged so nobody
    mistakes placeholders for real ratings."""
    sx.load_instructor_ratings.cache_clear()
    idx = sx.load_instructor_ratings()  # default path
    assert idx, "shipped instructor_ratings.csv failed to load"
    # Every shipped row must carry a provenance tag; placeholders must say so.
    sources = {rec["source"] for rec in idx.values()}
    assert sources, "no source tags found"
    assert any("placeholder" in s or s in {"rmp", "scu_eval", "manual"} for s in sources)


# ── Picker ───────────────────────────────────────────────────────────────────


def _section(num, instructors, days=(0, 2, 4), start=75, end=140):
    return {
        "section": num,
        "meeting_days": list(days),
        "meeting_start_min": start,
        "meeting_end_min": end,
        "instructors": list(instructors),
    }


def test_picker_chooses_highest_rated_instructor(monkeypatch):
    ratings = {
        "Low Prof": {"instructor": "Low Prof", "rating": 2.5, "difficulty": 3.0},
        "High Prof": {"instructor": "High Prof", "rating": 4.8, "difficulty": 2.0},
    }
    monkeypatch.setattr(
        graph_mod, "tool_get_instructor_rating",
        lambda name: ratings.get(name, {"instructor": name, "rating": None, "difficulty": None}),
    )
    sections = [
        _section(1, ["Low Prof"]),
        _section(2, ["High Prof"]),
    ]
    pick = graph_mod._select_best_section(sections)
    assert pick["instructor"] == "High Prof"
    assert pick["section"] == 2
    # The lower-rated instructor shows up as an alternative.
    alt_names = {a["instructor"] for a in pick["alternatives"]}
    assert "Low Prof" in alt_names


def test_picker_tiebreaks_on_lower_difficulty(monkeypatch):
    ratings = {
        "Hard Prof": {"instructor": "Hard Prof", "rating": 4.0, "difficulty": 4.5},
        "Easy Prof": {"instructor": "Easy Prof", "rating": 4.0, "difficulty": 2.0},
    }
    monkeypatch.setattr(
        graph_mod, "tool_get_instructor_rating",
        lambda name: ratings.get(name, {"instructor": name, "rating": None, "difficulty": None}),
    )
    sections = [_section(1, ["Hard Prof"]), _section(2, ["Easy Prof"])]
    pick = graph_mod._select_best_section(sections)
    assert pick["instructor"] == "Easy Prof", "same rating → lower difficulty wins"


def test_picker_stable_fallback_when_no_ratings(monkeypatch):
    monkeypatch.setattr(
        graph_mod, "tool_get_instructor_rating",
        lambda name: {"instructor": name, "rating": None, "difficulty": None},
    )
    sections = [_section(1, ["A Prof"]), _section(2, ["B Prof"])]
    pick = graph_mod._select_best_section(sections)
    # No data → deterministic: first section wins.
    assert pick["section"] == 1
    assert pick["instructor"] == "A Prof"


def test_picker_empty_sections_returns_none():
    assert graph_mod._select_best_section([]) is None
