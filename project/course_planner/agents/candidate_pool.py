"""Closed-world candidate pool for the constrained planner (v2).

The pool is the input contract for the deterministic schedule selector:
every recommendation MUST come from this list, indexed by integer ID.
The LLM (when used at all in v2) sees only the compact projection
returned by :meth:`CandidateCourse.to_llm_projection`; Python keeps the
full record (every offered section, instructor ratings, requirement
coverage, lab partner cross-references) for materialization later.

Design (see agents/planning_agent_v2.py for the engine that consumes
this):

    missing_details + completed + xlsx indexes
                      │
                      ▼
            build_candidate_pool()
                      │
                      ▼
       list[CandidateCourse]  +  must_cover labels

Hard requirements honored here, not by prompt prose:
  - completed courses are never in the pool;
  - lab partners are automatically pulled in when their lecture is in
    the pool (SCU's R1 lab/lecture pairing rule);
  - course titles and units come from ``load_course_titles_index`` /
    ``load_course_units_index`` (never the LLM);
  - sections come from ``load_all_course_sections`` so the selector can
    do real section-level conflict detection.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agents.planning_agent import (
    _normalize_open_req_text,
    _resolve_item_codes,
    _resolve_open_requirement,
)
from utils.academic_progress_helpers import default_units_for_code
from utils.enrichment_resolver import EDUCATIONAL_ENRICHMENT_MARKER
from utils.scu_course_schedule_xlsx import (
    course_title_for,
    course_units_for,
    load_all_course_sections,
    load_category_course_index,
    load_course_titles_index,
    load_course_units_index,
    load_instructor_ratings,
    load_schedule_section_index,
    planned_section_keys,
)

# Subjects whose trailing-L lab is taken in the same quarter as the lecture
# at SCU (AGENTS.md R1). Mirrors ``_LAB_PAIRING_SUBJECTS`` in planning_agent.
_LAB_SUBJECTS = frozenset(
    {"CSEN", "COEN", "CSCI", "ELEN", "ECEN", "PHYS", "CHEM", "BIOL", "MECH"}
)


def _is_educational_enrichment_requirement(item: dict[str, Any]) -> bool:
    """Educational Enrichment is self-managed; v2 does not auto-fill it."""
    text = " ".join(
        str(item.get(k) or "")
        for k in ("requirement", "category", "course")
    ).lower()
    return EDUCATIONAL_ENRICHMENT_MARKER in text


@dataclass(frozen=True)
class SectionOption:
    """One scheduled section for a course, with instructor rating attached."""

    section_number: int
    meeting_days: tuple[int, ...]
    meeting_start_min: int | None
    meeting_end_min: int | None
    instructor: str | None
    instructor_rating: float | None
    instructor_difficulty: float | None

    @property
    def has_meeting_time(self) -> bool:
        return (
            bool(self.meeting_days)
            and self.meeting_start_min is not None
            and self.meeting_end_min is not None
            and self.meeting_start_min < self.meeting_end_min
        )


@dataclass
class CandidateCourse:
    """A course the student could realistically take next quarter.

    ``categories_satisfied`` is the set of must-cover labels this course
    closes (e.g. ``"Major: CSEN 174"`` for a concrete requirement, or
    ``"rtc 3"`` for an open Core requirement). ``double_tagged`` is True
    when one course covers two or more labels — those are the highest-
    value picks (AGENTS.md R2).
    """

    id: int
    course_code: str
    title: str
    units: int
    categories_satisfied: tuple[str, ...]
    sections: tuple[SectionOption, ...]
    is_lab: bool
    lab_partner_code: str | None
    lab_partner_id: int | None = None
    kind: str = "required_specific"  # "required_specific" | "open_core" | "lab_companion"
    prereqs_met: bool = True

    @property
    def double_tagged(self) -> bool:
        return len(self.categories_satisfied) > 1

    @property
    def best_section(self) -> SectionOption | None:
        """Best section by instructor rating (desc), then difficulty (asc).

        Sections without a rated instructor sort last so a known-good
        instructor always wins. Falls back to the first section when no
        instructor data exists at all so a TBA course still has a pick.
        """
        if not self.sections:
            return None
        rated = [s for s in self.sections if s.instructor_rating is not None]
        pool = rated or list(self.sections)
        return sorted(
            pool,
            key=lambda s: (
                -(s.instructor_rating if s.instructor_rating is not None else -1.0),
                s.instructor_difficulty if s.instructor_difficulty is not None else 5.0,
                s.section_number,
            ),
        )[0]

    def to_llm_projection(self) -> dict[str, Any]:
        """Compact projection for the LLM ranking prompt (when used)."""
        best = self.best_section
        return {
            "id": self.id,
            "code": self.course_code,
            "title": self.title,
            "units": self.units,
            "covers": list(self.categories_satisfied),
            "covers_count": len(self.categories_satisfied),
            "double_tagged": self.double_tagged,
            "lab_partner_id": self.lab_partner_id,
            "best_instructor": best.instructor if best else None,
            "best_rating": best.instructor_rating if best else None,
            "best_difficulty": best.instructor_difficulty if best else None,
            "sections": len(self.sections),
            "kind": self.kind,
        }


def _section_options_for_code(
    code: str,
    all_sections: dict[tuple[str, str], list[dict[str, Any]]],
    ratings: dict[str, dict[str, Any]],
) -> tuple[SectionOption, ...]:
    seen: set[int] = set()
    out: list[SectionOption] = []
    for key in planned_section_keys(code):
        for sec in all_sections.get(key, []):
            n = int(sec.get("section") or 0)
            if n in seen:
                continue
            seen.add(n)
            instructors = sec.get("instructors") or []
            inst = instructors[0] if instructors else None
            rec = (
                ratings.get(inst) if inst else None
            ) or (ratings.get((inst or "").lower()) if inst else None) or {}
            try:
                rating = float(rec["rating"]) if rec.get("rating") is not None else None
            except (TypeError, ValueError):
                rating = None
            try:
                difficulty = (
                    float(rec["difficulty"]) if rec.get("difficulty") is not None else None
                )
            except (TypeError, ValueError):
                difficulty = None
            out.append(
                SectionOption(
                    section_number=n,
                    meeting_days=tuple(sec.get("meeting_days") or ()),
                    meeting_start_min=sec.get("meeting_start_min"),
                    meeting_end_min=sec.get("meeting_end_min"),
                    instructor=inst,
                    instructor_rating=rating,
                    instructor_difficulty=difficulty,
                )
            )
    return tuple(out)


def _normalize_code(code: str) -> str:
    return " ".join((code or "").split()).upper()


def _is_offered(code: str, schedule_index: dict) -> bool:
    return any(k in schedule_index for k in planned_section_keys(code))


# Senior Design capstone sequence (192 → 194 → 195 → 196 and the co-listed
# ENGR variants). These are final-year courses with deep, often-implicit
# prerequisites the closed-world pool cannot see. A student who has barely
# started their degree must never be handed a capstone even when Workday
# still lists it as unsatisfied — so we gate these behind a minimum count of
# completed courses (roughly "past the sophomore year"). This is a
# deliberately coarse floor; precise final-year placement is handled
# separately by ``enforce_senior_design_in_final_quarters`` in the 4-year
# planner. The threshold compares against the alias-expanded completed set
# the engine passes in.
_SENIOR_DESIGN_SUBJECTS = frozenset(
    {"CSEN", "COEN", "ECEN", "ELEN", "MECH", "ENGR", "CENG", "BIOE"}
)
_SENIOR_DESIGN_NUMS = frozenset({"192", "194", "195", "196"})
_SENIOR_DESIGN_MIN_COMPLETED = 15


def _is_senior_design_code(code: str) -> bool:
    parts = _normalize_code(code).split()
    if len(parts) != 2:
        return False
    subj, num = parts
    base = num[:-1] if num.endswith("L") and len(num) > 1 else num
    return subj in _SENIOR_DESIGN_SUBJECTS and base in _SENIOR_DESIGN_NUMS


def _senior_design_gated(code: str, completed_codes: set[str]) -> bool:
    """True when ``code`` is a Senior Design capstone and the student has not
    completed enough courses to plausibly be in their final year."""
    if not _is_senior_design_code(code):
        return False
    return len(completed_codes) < _SENIOR_DESIGN_MIN_COMPLETED


def build_candidate_pool(
    missing_details: list[dict[str, Any]],
    completed_codes: set[str],
    user_preference: str = "",
    *,
    schedule_index: dict | None = None,
    category_index: dict | None = None,
    titles_index: dict | None = None,
    units_index: dict | None = None,
    all_sections: dict | None = None,
    ratings: dict | None = None,
) -> tuple[list[CandidateCourse], list[str]]:
    """Build the candidate pool plus the list of must-cover labels.

    All xlsx indexes are loaded lazily when not injected; tests inject
    them to avoid touching disk. Lab partners are auto-added so the
    selector can pair them; ``categories_satisfied`` is aggregated when
    one course satisfies multiple open requirements (R2 double tagging).

    Returns ``(candidates, must_cover)``; ``candidate.id`` matches the
    list index so callers can look up by integer.
    """
    schedule_index = (
        schedule_index if schedule_index is not None else load_schedule_section_index()
    )
    category_index = (
        category_index if category_index is not None else load_category_course_index()
    )
    titles_index = (
        titles_index if titles_index is not None else load_course_titles_index()
    )
    units_index = (
        units_index if units_index is not None else load_course_units_index()
    )
    all_sections = (
        all_sections if all_sections is not None else load_all_course_sections()
    )
    ratings = ratings if ratings is not None else load_instructor_ratings()

    # Step 1: gather (code -> [requirement labels]) and the set of must-cover
    # labels. Concrete-code requirements become "Major: CSEN 174". Open Core
    # requirements use the normalised label (e.g. "rtc 3"); multiple courses
    # can cover one open label, and one course can cover multiple labels
    # (the double-tag case).
    code_to_categories: dict[str, list[str]] = {}
    must_cover: list[str] = []
    must_cover_seen: set[str] = set()

    def _push_must_cover(label: str) -> None:
        if label and label not in must_cover_seen:
            must_cover.append(label)
            must_cover_seen.add(label)

    for item in missing_details or []:
        if not isinstance(item, dict):
            continue
        if _is_educational_enrichment_requirement(item):
            continue
        codes = _resolve_item_codes(item)
        # ``_resolve_item_codes`` is permissive: for "Core: ENGR: RTC 3" it
        # returns ["RTC 3"], which looks like a course code but is really
        # an open-requirement *label*. We treat any extracted "code" that
        # isn't actually in the schedule as a signal to fall through to
        # the open-Core resolver instead of declaring it not-offered.
        offered_codes = [c for c in codes if _is_offered(_normalize_code(c), schedule_index)]
        if offered_codes:
            # Concrete requirement: e.g. {"course": "CSEN 174", "category": "Major"}.
            # The first offered code is the canonical one; any alias
            # (CSEN/COEN) is already cross-listed in schedule_index.
            primary = _normalize_code(offered_codes[0])
            if primary in completed_codes:
                continue
            # Grade-gate Senior Design: a student who has barely started
            # must not be handed a final-year capstone even when Workday
            # still lists it unsatisfied. Skipping here keeps it out of the
            # pool entirely (same effect as a completed/not-offered course),
            # so it is never recommended this quarter. AGENTS.md plan A.
            if _senior_design_gated(primary, completed_codes):
                continue
            label = f"Major: {primary}"
            code_to_categories.setdefault(primary, [])
            if label not in code_to_categories[primary]:
                code_to_categories[primary].append(label)
            _push_must_cover(label)
        else:
            req_text = (item.get("category") or item.get("requirement") or "").strip()
            if not req_text:
                continue
            label = _normalize_open_req_text(req_text) or req_text[:40]
            open_courses = _resolve_open_requirement(
                req_text,
                category_index,
                schedule_index,
                user_preference=user_preference,
            )
            if not open_courses:
                # The requirement parser found no offered course for this
                # open Core slot. Don't add to must_cover; the engine
                # surfaces it as a deferred requirement with a reason.
                continue
            for c in open_courses:
                c_norm = _normalize_code(c)
                if c_norm in completed_codes:
                    continue
                code_to_categories.setdefault(c_norm, [])
                if label not in code_to_categories[c_norm]:
                    code_to_categories[c_norm].append(label)
            _push_must_cover(label)

    # Step 2: auto-add lab partners. If the lecture is in the pool and its
    # trailing-L lab is offered, the lab joins the pool with the lecture's
    # categories (a lab-companion candidate). And vice versa: if the LLM-style
    # missing_details happened to include only the lab, drop in the lecture.
    extras: dict[str, list[str]] = {}
    for code, cats in code_to_categories.items():
        parts = code.split()
        if len(parts) != 2:
            continue
        subj, num = parts
        if subj not in _LAB_SUBJECTS:
            continue
        if num.endswith("L") and len(num) > 1:
            partner = f"{subj} {num[:-1]}"
        else:
            partner = f"{subj} {num}L"
        if partner in code_to_categories or partner in extras:
            continue
        if partner in completed_codes:
            continue
        if not _is_offered(partner, schedule_index):
            continue
        extras[partner] = list(cats)
    for code, cats in extras.items():
        code_to_categories[code] = cats

    # Step 3: build CandidateCourse records.
    candidates: list[CandidateCourse] = []
    code_to_id: dict[str, int] = {}

    for code, cats in code_to_categories.items():
        title = course_title_for(code, titles_index) or code
        units = course_units_for(code, units_index)
        if units is None:
            units = default_units_for_code(code, {})
        secs = _section_options_for_code(code, all_sections, ratings)
        subj = code.split(" ", 1)[0]
        num = code.split(" ", 1)[1] if " " in code else ""
        is_lab = num.endswith("L") and len(num) > 1

        # Lab partner discovery (used to cross-reference IDs after the
        # whole pool has been built).
        lab_partner: str | None = None
        if subj in _LAB_SUBJECTS:
            partner_num = num[:-1] if is_lab else f"{num}L"
            partner = f"{subj} {partner_num}"
            if _is_offered(partner, schedule_index):
                lab_partner = partner

        # Classify the candidate. Lab-companion when this entry was only
        # added because its lecture was a real requirement.
        kind = "required_specific"
        if all(c.startswith("Major: ") for c in cats):
            kind = "required_specific"
        elif cats:
            kind = "open_core"
        if code in extras:
            kind = "lab_companion"

        cand = CandidateCourse(
            id=len(candidates),
            course_code=code,
            title=title,
            units=int(units),
            categories_satisfied=tuple(cats),
            sections=secs,
            is_lab=is_lab,
            lab_partner_code=lab_partner,
            kind=kind,
        )
        candidates.append(cand)
        code_to_id[code] = cand.id

    # Step 4: backfill lab_partner_id once IDs are stable.
    for cand in candidates:
        if cand.lab_partner_code and cand.lab_partner_code in code_to_id:
            cand.lab_partner_id = code_to_id[cand.lab_partner_code]

    return candidates, list(must_cover)
