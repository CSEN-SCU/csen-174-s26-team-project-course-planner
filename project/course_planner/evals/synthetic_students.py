"""Synthetic grade-level students for recommendation-quality analysis.

Goal: probe whether the planner recommends *grade-appropriate* courses.
A freshman should be steered into intro/lower-division work and must NOT be
handed Senior Design; a senior who has cleared most requirements should be
offered Senior Design (192 → 194 → 195 → 196).

Design — generic + honest, no per-major hand-tuning:
  A student is modeled as having linearly progressed through their major's
  required-course sequence. We sort the major's ``required_courses`` by
  ``(is_senior_design, course_number, is_lab)`` so Senior Design always sorts
  last, then split:

      freshman  → 0%   completed   (everything remains)
      sophomore → 25%  completed
      junior    → 55%  completed
      senior    → 80%  completed   (only the upper tail, incl. Senior Design)

  ``completed_course_codes`` = the completed prefix.
  ``missing_details``        = the remaining courses, as Workday-style
                               "Not Satisfied" requirement rows.

The split fractions are intentionally coarse: the eval's assertions are about
*internal consistency* (no completed course re-recommended, units within the
hard cap, Senior Design placed only for seniors), not about reproducing one
exact transcript.
"""

from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

_INDEX_PATH = Path(__file__).resolve().parents[1] / "data" / "majors" / "index.json"

# Fraction of the required-course sequence a student at each grade has cleared.
_GRADE_PROGRESS: dict[str, float] = {
    "freshman": 0.0,
    "sophomore": 0.25,
    "junior": 0.55,
    "senior": 0.80,
}

_SENIOR_DESIGN_NUMS = {"192", "193", "194", "195", "196", "199"}
_CODE_RE = re.compile(r"^([A-Z]{2,6})\s+(\d{1,3})([A-Z]?)$")


@dataclass
class SyntheticStudent:
    major_id: str
    grade: str
    completed_course_codes: list[str]
    missing_details: list[dict[str, Any]]


@lru_cache(maxsize=1)
def _major_index() -> dict[str, dict[str, Any]]:
    with _INDEX_PATH.open(encoding="utf-8") as f:
        data = json.load(f)
    return {e["major_id"]: e for e in data.get("majors", [])}


def _sort_key(code: str) -> tuple[int, int, int]:
    """(is_senior_design, course_number, is_lab) — Senior Design sorts last."""
    m = _CODE_RE.match(code)
    if not m:
        return (1, 999, 0)
    num, suffix = m.group(2), m.group(3)
    is_sd = 1 if num in _SENIOR_DESIGN_NUMS else 0
    is_lab = 1 if suffix == "L" else 0
    return (is_sd, int(num), is_lab)


def ordered_required(major_id: str) -> list[str]:
    """Major's required courses, de-duped and ordered freshman→senior."""
    entry = _major_index().get(major_id) or {}
    required = list(entry.get("required_courses") or [])
    for code in entry.get("senior_design_sequence") or []:
        if code not in required:
            required.append(code)
    seen: set[str] = set()
    uniq: list[str] = []
    for c in required:
        cu = c.strip().upper()
        if cu and cu not in seen:
            seen.add(cu)
            uniq.append(cu)
    return sorted(uniq, key=_sort_key)


def make_student(major_id: str, grade: str) -> SyntheticStudent:
    if grade not in _GRADE_PROGRESS:
        raise ValueError(f"unknown grade {grade!r}; expected {list(_GRADE_PROGRESS)}")
    seq = ordered_required(major_id)
    cut = int(round(len(seq) * _GRADE_PROGRESS[grade]))
    completed = seq[:cut]
    remaining = seq[cut:]
    name = (_major_index().get(major_id) or {}).get("name", major_id.upper())
    missing_details = [
        {
            "requirement": f"{name} Major: {code}",
            "course": code,
            "status": "Not Satisfied",
        }
        for code in remaining
    ]
    return SyntheticStudent(
        major_id=major_id,
        grade=grade,
        completed_course_codes=completed,
        missing_details=missing_details,
    )


def all_grades() -> list[str]:
    return list(_GRADE_PROGRESS.keys())


def make_fuzz_student(major_id: str, seed: int) -> SyntheticStudent:
    """A randomized, possibly out-of-order transcript for stress testing.

    Unlike ``make_student`` (a clean linear prefix), this completes a RANDOM
    subset of the major's required courses — modeling a real student who
    took courses out of the ideal order, transferred credit, or has gaps.
    The fraction completed is itself randomized (10%–90%) so a single seed
    sweep covers early, mid, and late students. ``grade`` is labeled by the
    completed fraction so downstream checks (e.g. freshman_no_senior_design)
    still apply.

    Deterministic per ``seed`` so a failing fuzz case is reproducible.
    """
    rng = random.Random(seed)
    seq = ordered_required(major_id)
    if not seq:
        return SyntheticStudent(major_id, "fuzz", [], [])

    frac = rng.uniform(0.1, 0.9)
    k = int(round(len(seq) * frac))
    completed = rng.sample(seq, k)  # random subset, NOT a clean prefix
    completed_set = set(completed)
    remaining = [c for c in seq if c not in completed_set]

    # Label a grade band from the completed fraction so grade-appropriate
    # checks (Senior Design gating) still have a meaningful target.
    if frac < 0.15:
        grade = "freshman"
    elif frac < 0.4:
        grade = "sophomore"
    elif frac < 0.7:
        grade = "junior"
    else:
        grade = "senior"

    name = (_major_index().get(major_id) or {}).get("name", major_id.upper())
    missing_details = [
        {
            "requirement": f"{name} Major: {code}",
            "course": code,
            "status": "Not Satisfied",
        }
        for code in remaining
    ]
    return SyntheticStudent(
        major_id=major_id,
        grade=grade,
        completed_course_codes=completed,
        missing_details=missing_details,
    )
