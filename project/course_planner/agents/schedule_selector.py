"""Deterministic schedule selector for the constrained planner.

Picks the best feasible course set from a ``CandidateCourse`` pool given
hard constraints (no time conflicts, lab partners co-selected, unit
band) and soft scoring (requirement coverage, double-tag bonus,
instructor rating, preference keywords).

This module replaces what the legacy planning agent asks the LLM to do:
combinatorial constraint solving. The LLM is bad at it; Python is fast
and correct. The selector is pure Python, deterministic, and runs in
single-digit milliseconds on real candidate pools (20-60 candidates).

Hard constraints (must hold):
  - no time conflicts among picked sections;
  - lab partners co-selected when both are in the pool;
  - total units in ``[unit_min, hard_max]`` (when a feasible plan
    exists);
  - candidate.prereqs_met == True (currently always True since the
    planner has no transcript prereq data yet; placeholder for the
    future).

Soft scoring (highest score wins):
  - +5 per must-cover label closed;
  - +2 per extra category satisfied (R2 double-tag bonus);
  - +instructor_rating of the chosen section's lead;
  - small preference adjustments (no-morning, light-load).

Locks (R7 follow-up support): callers can pass ``locked_codes`` to pin
courses from the previous plan; the selector treats them as
pre-selected and fills the remaining unit budget around them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from agents.candidate_pool import CandidateCourse, SectionOption

# Hard branch budget so a pathological pool can't hang the request. Real
# pools resolve in <100 branches; 50k is a comfortable cushion.
_MAX_BRANCHES = 50_000

# Coverage weights: major/catalog requirements outrank open Core/GE slots so
# one quarter fills CSEN/COEN/MATH rows before packing unrelated GE electives.
_MAJOR_COVERAGE_WEIGHT = 12.0
_OPEN_COVERAGE_WEIGHT = 5.0


def _coverage_weight(label: str) -> float:
    return _MAJOR_COVERAGE_WEIGHT if label.startswith("Major: ") else _OPEN_COVERAGE_WEIGHT


def _major_label_count(categories: Iterable[str]) -> int:
    return sum(1 for cat in categories if cat.startswith("Major: "))

_NO_MORNING_RE = re.compile(
    r"no\s+(?:early|morning)|after\s+10|after\s+9|nothing\s+(?:early|before)",
    re.IGNORECASE,
)
_PREFER_AFTERNOON_RE = re.compile(
    r"prefer\s+afternoon|afternoon\s+(?:classes|only)",
    re.IGNORECASE,
)
_LIGHT_LOAD_RE = re.compile(r"light\s+(?:load|quarter)|easy\s+quarter", re.IGNORECASE)


@dataclass
class SelectionResult:
    """Outcome of one ``select_schedule`` call."""

    selected: list[CandidateCourse]
    chosen_sections: dict[int, SectionOption]  # candidate.id -> section
    score: float
    deferred: list[dict[str, str]]
    branches_explored: int = 0


def _section_conflict(a: SectionOption, b: SectionOption) -> bool:
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


def _preference_score(section: SectionOption, pref: str) -> float:
    """Soft scoring for natural-language preferences. Small numbers so
    hard coverage always dominates."""
    score = 0.0
    if section.meeting_start_min is None:
        return score
    if _NO_MORNING_RE.search(pref) and section.meeting_start_min < 60:
        # Calendar offsets are minutes-from-8AM; 60 = 9AM.
        score -= 1.0
    if _PREFER_AFTERNOON_RE.search(pref) and section.meeting_start_min < 240:
        # 240 = noon offset
        score -= 0.5
    if _LIGHT_LOAD_RE.search(pref):
        diff = section.instructor_difficulty
        if diff is not None and diff > 3.5:
            score -= 0.5
    return score


def _best_nonconflicting_section(
    course: CandidateCourse,
    already_chosen: dict[int, SectionOption],
    user_preference: str,
) -> SectionOption | None:
    """Pick the highest-rated section that doesn't conflict with
    anything already chosen. Falls back to None when every section
    conflicts (selector will then skip the candidate)."""
    others = list(already_chosen.values())
    ranked = sorted(
        course.sections,
        key=lambda s: (
            -(s.instructor_rating if s.instructor_rating is not None else -1.0),
            s.instructor_difficulty if s.instructor_difficulty is not None else 5.0,
            -_preference_score(s, user_preference),
            s.section_number,
        ),
    )
    for sec in ranked:
        if not any(_section_conflict(sec, o) for o in others):
            return sec
    return None


def _score(
    selected: Iterable[CandidateCourse],
    chosen: dict[int, SectionOption],
    must_cover_set: set[str],
    user_preference: str,
) -> float:
    """Score function. Higher is better.

    Three rules baked in:
      1. Coverage is set-based: covering the same label twice doesn't
         add a second +5.
      2. Rating bonus is only credited for courses that *newly* close a
         must-cover label. A redundant 4.0-rated course adds no rating
         bonus, only the per-course penalty below.
      3. Per-course penalty (-1.0) so a leaner plan that still hits
         ``unit_min`` and covers everything beats a redundant heavier
         one. Lab partners share the penalty because they're
         inseparable pairs (R1).

    Order-dependent (which course "wins" credit for a shared label
    matters), but the selector always traverses candidates in the same
    greedy order so the score is deterministic for any given pool.
    """
    selected = list(selected)
    cats_covered: set[str] = set()
    coverage = 0.0
    double_bonus = 0.0
    rating_sum = 0.0
    pref_sum = 0.0
    for c in selected:
        sec = chosen.get(c.id)
        new_cats = (set(c.categories_satisfied) & must_cover_set) - cats_covered
        if new_cats:
            cats_covered |= new_cats
            coverage += sum(_coverage_weight(cat) for cat in new_cats)
            double_bonus += max(0, len(c.categories_satisfied) - 1) * 2.0
            if sec is not None and sec.instructor_rating is not None:
                rating_sum += sec.instructor_rating
        if sec is not None:
            pref_sum += _preference_score(sec, user_preference)
    return coverage + double_bonus + rating_sum + pref_sum - 1.0 * len(selected)


def select_schedule(
    candidates: list[CandidateCourse],
    must_cover: list[str],
    *,
    user_preference: str = "",
    unit_min: int = 12,
    unit_max: int = 16,
    hard_max: int = 20,
    max_courses: int = 6,
    locked_codes: set[str] | None = None,
) -> SelectionResult:
    """Pick the best-score feasible course set.

    Branch-and-bound over candidates sorted by coverage + rating. Prunes
    on unit_max, max_courses, and a hard branch budget. Early-accepts
    any feasible plan ≥ ``unit_min`` and updates the best-so-far when a
    higher score is found.

    R7 support: ``locked_codes`` (course codes from the previous plan
    the user did NOT name for removal) are pre-selected and never
    branched on; the selector fills the remaining budget around them.
    """
    must_cover_set = set(must_cover or [])
    locked_codes = locked_codes or set()

    # Step 1: pre-select locks. Their sections get fixed up front; if a
    # lock has no candidate entry (e.g. the user previously added a
    # course that's no longer offered) we skip it gracefully.
    pre_chosen: dict[int, SectionOption] = {}
    pre_selected: list[CandidateCourse] = []
    pre_units = 0
    pool: list[CandidateCourse] = []
    for c in candidates:
        if not c.prereqs_met or not c.sections:
            continue
        if c.course_code in locked_codes:
            sec = _best_nonconflicting_section(c, pre_chosen, user_preference)
            if sec is None:
                # Couldn't fit a locked section; keep it as a regular
                # branchable candidate so we at least try.
                pool.append(c)
                continue
            pre_chosen[c.id] = sec
            pre_selected.append(c)
            pre_units += c.units
        else:
            pool.append(c)

    # Step 2: greedy sort by (most coverage, then highest rating). This
    # makes the first DFS path a good plan, which the rest of the search
    # then tries to beat.
    pool.sort(
        key=lambda c: (
            -_major_label_count(c.categories_satisfied),
            -len(c.categories_satisfied),
            -(c.best_section.instructor_rating if c.best_section and c.best_section.instructor_rating is not None else -1.0),
            c.units,
        )
    )

    best: SelectionResult | None = None
    branches = [0]  # mutable counter; closure-captured

    def _maybe_record(selected: list[CandidateCourse], chosen: dict[int, SectionOption], units: int) -> None:
        nonlocal best
        sc = _score(selected, chosen, must_cover_set, user_preference)
        if best is None or sc > best.score:
            best = SelectionResult(
                selected=list(selected),
                chosen_sections=dict(chosen),
                score=sc,
                deferred=[],
                branches_explored=branches[0],
            )

    def _ranked_sections(c: CandidateCourse) -> list[SectionOption]:
        return sorted(
            c.sections,
            key=lambda s: (
                -(s.instructor_rating if s.instructor_rating is not None else -1.0),
                s.instructor_difficulty if s.instructor_difficulty is not None else 5.0,
                -_preference_score(s, user_preference),
                s.section_number,
            ),
        )

    def _try_pair_lab(
        lecture: CandidateCourse,
        chosen: dict[int, SectionOption],
        units: int,
    ) -> tuple[CandidateCourse, SectionOption] | None:
        """Find a feasible lab-partner section, if any."""
        if lecture.lab_partner_id is None or lecture.lab_partner_id in chosen:
            return None
        partner = next((p for p in candidates if p.id == lecture.lab_partner_id), None)
        if partner is None:
            return None
        if units + partner.units > hard_max:
            return None
        for psec in _ranked_sections(partner):
            if not any(_section_conflict(psec, o) for o in chosen.values()):
                return partner, psec
        return None

    def _recurse(
        i: int,
        selected: list[CandidateCourse],
        chosen: dict[int, SectionOption],
        units: int,
    ) -> None:
        if branches[0] >= _MAX_BRANCHES:
            return
        if units > hard_max or len(selected) > max_courses:
            return
        if units >= unit_min:
            _maybe_record(selected, chosen, units)
        if i >= len(pool):
            return
        branches[0] += 1

        c = pool[i]
        # Branch A: try including candidate ``c`` at each non-conflicting
        # section. Section choice matters: section 1 might conflict with
        # something already chosen while section 2 doesn't, so we must
        # backtrack across sections.
        if c.id not in chosen and units + c.units <= hard_max:
            for sec in _ranked_sections(c):
                if any(_section_conflict(sec, o) for o in chosen.values()):
                    continue
                chosen[c.id] = sec
                selected.append(c)
                pair = _try_pair_lab(c, chosen, units + c.units)
                if pair is not None:
                    partner, psec = pair
                    chosen[partner.id] = psec
                    selected.append(partner)
                    _recurse(i + 1, selected, chosen, units + c.units + partner.units)
                    selected.pop()
                    del chosen[partner.id]
                elif c.lab_partner_id is None or c.lab_partner_id in chosen:
                    # No lab partner needed (or already placed): recurse
                    # without pairing.
                    _recurse(i + 1, selected, chosen, units + c.units)
                # If the candidate had an unmet lab partner that didn't
                # fit, we DO NOT pick this candidate here; lab pairs are
                # inseparable.
                selected.pop()
                del chosen[c.id]

        # Branch B: skip this candidate.
        _recurse(i + 1, selected, chosen, units)

    _recurse(0, list(pre_selected), dict(pre_chosen), pre_units)

    if best is None:
        # No feasible plan at unit_min. Return whatever the locks gave
        # us (might be 0 courses) so the caller can surface
        # deferred_requirements with a real reason.
        return SelectionResult(
            selected=list(pre_selected),
            chosen_sections=dict(pre_chosen),
            score=_score(pre_selected, pre_chosen, must_cover_set, user_preference),
            deferred=[{"requirement": r, "reason": "no feasible plan in unit/conflict constraints"} for r in must_cover],
            branches_explored=branches[0],
        )

    covered: set[str] = set()
    for c in best.selected:
        covered.update(c.categories_satisfied)
    best.deferred = [
        {"requirement": r, "reason": "no candidate fit unit/conflict constraints"}
        for r in must_cover
        if r not in covered
    ]
    return best
