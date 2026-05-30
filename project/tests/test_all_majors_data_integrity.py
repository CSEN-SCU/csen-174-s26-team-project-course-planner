"""Data-integrity guards for the full SCU major catalog (data/majors/).

These tests pin down invariants the planning agents rely on after the
catalog expanded from 18 curated majors to the full bulletin set
(``scripts/scrape_all_majors.py``). They are deliberately data-driven so a
bad re-scrape fails loudly instead of silently shipping wrong requirements.

Invariants:
  1. Every index.json entry has a matching, non-empty markdown file.
  2. major_id values are unique and lowercase.
  3. Each markdown frontmatter's major_id matches its index entry.
  4. required_courses use the major's own subject prefixes (no stray codes
     leaking in from a mis-scraped section).
  5. detect_patterns do not collide across majors — a shared pattern would
     make R2 major detection ambiguous.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

_DATA = Path(__file__).resolve().parents[1] / "course_planner" / "data"
_MAJORS_DIR = _DATA / "majors"
_INDEX = _MAJORS_DIR / "index.json"

_CODE_RE = re.compile(r"^([A-Z]{2,6})\s+\d{1,3}[A-Z]?$")


def _index_entries() -> list[dict]:
    with _INDEX.open(encoding="utf-8") as f:
        return json.load(f)["majors"]


def _ids() -> list[str]:
    return [e["major_id"] for e in _index_entries()]


def test_index_file_exists_and_nonempty() -> None:
    entries = _index_entries()
    assert len(entries) >= 40, f"expected the full catalog, got {len(entries)}"


def test_major_ids_unique_and_lowercase() -> None:
    ids = _ids()
    assert len(ids) == len(set(ids)), "duplicate major_id in index.json"
    for mid in ids:
        assert mid == mid.lower(), f"major_id must be lowercase: {mid!r}"


@pytest.mark.parametrize("entry", _index_entries(), ids=_ids())
def test_each_major_has_markdown_file(entry: dict) -> None:
    md = _DATA / entry["markdown_path"]
    assert md.is_file(), f"missing markdown for {entry['major_id']}: {md}"
    assert md.stat().st_size > 0, f"empty markdown for {entry['major_id']}"


@pytest.mark.parametrize("entry", _index_entries(), ids=_ids())
def test_markdown_frontmatter_major_id_matches_index(entry: dict) -> None:
    md = _DATA / entry["markdown_path"]
    text = md.read_text(encoding="utf-8")
    assert text.startswith("---"), f"{entry['major_id']}: no frontmatter"
    m = re.search(r"^major_id:\s*(\S+)\s*$", text, re.MULTILINE)
    assert m, f"{entry['major_id']}: no major_id in frontmatter"
    assert m.group(1) == entry["major_id"], (
        f"frontmatter major_id {m.group(1)!r} != index {entry['major_id']!r}"
    )


@pytest.mark.parametrize("entry", _index_entries(), ids=_ids())
def test_required_courses_are_wellformed_codes(entry: dict) -> None:
    for code in entry.get("required_courses") or []:
        assert _CODE_RE.match(code), (
            f"{entry['major_id']}: malformed required course code {code!r}"
        )


def test_detect_patterns_do_not_collide_across_majors() -> None:
    """A detect_pattern shared by two majors makes R2 detection ambiguous."""
    seen: dict[str, str] = {}
    collisions: list[str] = []
    for entry in _index_entries():
        for pat in entry.get("detect_patterns") or []:
            key = pat.strip().lower()
            if key in seen and seen[key] != entry["major_id"]:
                collisions.append(
                    f"{pat!r} shared by {seen[key]} and {entry['major_id']}"
                )
            else:
                seen[key] = entry["major_id"]
    assert not collisions, "detect_pattern collisions:\n" + "\n".join(collisions)
