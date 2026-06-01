"""Educational Enrichment (major): department-sequence course resolution.

Unlike Core/GE open requirements (Course Tags in the schedule xlsx), enrichment
for COEN/CSE-style programs is typically "three courses in the same department"
(e.g. three HIST courses). Students describe direction in natural language or by
naming a department prefix rather than a specific catalog code.

This module is deterministic (no LLM). Planning and slot-suggestion endpoints
call it to list next-term candidates.
"""

from __future__ import annotations

import re
from typing import Any

EDUCATIONAL_ENRICHMENT_MARKER = "educational enrichment"

# Departments the pipeline must never auto-select for Educational Enrichment.
_BLOCKED_ENRICHMENT_SUBJECTS = frozenset({"CHIN"})

_COURSE_CODE_RE = re.compile(r"^([A-Z]{2,8})\s+(\d+[A-Z]?)$", re.IGNORECASE)


def requirement_text_from_detail(detail: dict[str, Any]) -> str:
    for key in ("requirement", "category", "name", "label"):
        v = detail.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def has_educational_enrichment_gap(missing_details: list[dict[str, Any]] | None) -> bool:
    for detail in missing_details or []:
        if not isinstance(detail, dict):
            continue
        if EDUCATIONAL_ENRICHMENT_MARKER in requirement_text_from_detail(detail).lower():
            return True
    return False


def infer_enrichment_subjects(user_preference: str) -> list[str]:
    """Infer department prefix(es) from free-form text (e.g. HIST → HIST)."""
    text = (user_preference or "").strip()
    if not text:
        return []
    u = text.upper()
    out: list[str] = []
    seen: set[str] = set()

    for m in re.finditer(r"\b([A-Z]{2,6})\b", u):
        subj = m.group(1)
        if subj.isalpha() and 2 <= len(subj) <= 6 and subj not in seen:
            out.append(subj)
            seen.add(subj)

    return [s for s in out[:3] if s not in _BLOCKED_ENRICHMENT_SUBJECTS]


def enrichment_track_label(subjects: list[str]) -> str:
    """Human-facing label for the active enrichment direction."""
    if not subjects:
        return ""
    return " / ".join(subjects)


def _split_course_code(code: str) -> tuple[str, str] | None:
    m = _COURSE_CODE_RE.match(" ".join(code.split()).upper())
    if not m:
        return None
    return m.group(1), m.group(2)


def course_matches_enrichment_track(
    course_code: str,
    title: str | None,
    subjects: list[str],
) -> bool:
    """True if *course_code* fits the enrichment direction (department prefix)."""
    if not subjects:
        return False
    parts = _split_course_code(course_code)
    if not parts:
        return False
    subj, _num = parts
    return subj in subjects


def list_enrichment_course_codes(
    schedule_index: dict[tuple[str, str], dict[str, Any]],
    subjects: list[str],
    titles_index: dict[tuple[str, str], str] | None = None,
    *,
    exclude_codes: list[str] | None = None,
) -> list[str]:
    """All next-term course codes matching the enrichment department/direction."""
    if not schedule_index or not subjects:
        return []
    exclude = {c.strip().upper() for c in (exclude_codes or [])}
    titles_index = titles_index or {}
    codes: list[str] = []
    seen: set[str] = set()

    for (subj, num) in schedule_index.keys():
        code = f"{subj} {num}"
        if code in exclude or code in seen:
            continue
        title = titles_index.get((subj, num)) or titles_index.get((subj, num.upper()))
        if course_matches_enrichment_track(code, title, subjects):
            codes.append(code)
            seen.add(code)

    return codes


_ENRICHMENT_INTENT_RE = re.compile(
    r"\b(enrichment|enrichments)\b",
    re.IGNORECASE,
)


def user_mentions_enrichment(user_preference: str) -> bool:
    """True when the student is talking about major Educational Enrichment."""
    text = user_preference or ""
    if _ENRICHMENT_INTENT_RE.search(text):
        return True
    return "充实" in text


def should_show_slot_enrichment(
    user_preference: str,
    missing_details: list[dict[str, Any]] | None,
    *,
    plan_course_codes: list[str] | None = None,
) -> bool:
    """Whether the slot popover should show the Enrichment section."""
    if has_educational_enrichment_gap(missing_details):
        return True
    if user_mentions_enrichment(user_preference):
        return True
    subjects = infer_enrichment_subjects(user_preference)
    if subjects:
        return True
    return False


def should_run_enrichment_followup(
    user_preference: str,
    missing_details: list[dict[str, Any]] | None,
) -> bool:
    """Whether a follow-up should append an enrichment-track course deterministically."""
    if not infer_enrichment_subjects(user_preference):
        return False
    return has_educational_enrichment_gap(missing_details) or user_mentions_enrichment(
        user_preference
    )


def try_enrichment_followup_plan(
    *,
    user_preference: str,
    missing_details: list[dict[str, Any]] | None,
    previous_plan: dict[str, Any],
    units_lookup: dict[str, int] | None = None,
) -> dict[str, Any] | None:
    """Append one enrichment-direction course to CURRENT STATE without calling the LLM.

    Returns a full planning-agent-shaped dict, or None when this path does not apply.
  """
    if not isinstance(previous_plan, dict):
        return None
    prev_recs = previous_plan.get("recommended") or []
    if not isinstance(prev_recs, list) or not prev_recs:
        return None
    if not should_run_enrichment_followup(user_preference, missing_details):
        return None

    subjects = infer_enrichment_subjects(user_preference)
    if not subjects:
        return None

    # Lazy imports keep this module importable without google.genai.
    from utils.academic_progress_helpers import default_units_for_code
    from utils.scu_course_schedule_xlsx import (
        course_title_for,
        course_units_for,
        detect_time_conflicts,
        load_course_titles_index,
        load_course_units_index,
        load_instructor_ratings,
        load_schedule_section_index,
    )

    def _norm(code: str | None) -> str:
        return " ".join(str(code or "").split()).upper()

    schedule_index = load_schedule_section_index()
    if not schedule_index:
        return None

    titles_index = load_course_titles_index()
    units_index = load_course_units_index()
    ratings = load_instructor_ratings()
    lookup = units_lookup or {}

    existing_codes = {
        _norm((r or {}).get("course") if isinstance(r, dict) else "") for r in prev_recs
    }
    existing_codes.discard("")

    enrich_codes = list_enrichment_course_codes(
        schedule_index,
        subjects,
        titles_index,
        exclude_codes=list(existing_codes),
    )

    from utils.scu_course_schedule_xlsx import planned_section_keys

    def _best_rating(code: str) -> float:
        best = -1.0
        for key in planned_section_keys(code):
            entry = schedule_index.get(key) or {}
            for name in entry.get("instructors") or []:
                rec = ratings.get(name) or ratings.get((name or "").lower())
                if rec and rec.get("rating") is not None:
                    try:
                        best = max(best, float(rec["rating"]))
                    except (TypeError, ValueError):
                        pass
        return best

    enrich_codes.sort(key=_best_rating, reverse=True)

    base_codes = [
        _norm((r or {}).get("course") if isinstance(r, dict) else "")
        for r in prev_recs
        if isinstance(r, dict) and _norm(r.get("course"))
    ]

    track = enrichment_track_label(subjects)
    chosen: str | None = None
    for code in enrich_codes:
        if schedule_index and detect_time_conflicts(base_codes + [code], schedule_index):
            continue
        chosen = code
        break

    if not chosen:
        total = sum(
            int((r or {}).get("units") or 0)
            for r in prev_recs
            if isinstance(r, dict)
        )
        return {
            "recommended": list(prev_recs),
            "total_units": total,
            "advice": (
                f"No available {track} courses found next term, or they all have time conflicts."
            ),
            "assistant_reply": (
                f"No, I could not add a {track} course for next term — none are available "
                f"without a time conflict. Your current plan is unchanged."
            ),
        }

    units = course_units_for(chosen, units_index) or default_units_for_code(chosen, lookup)
    new_item = {
        "course": chosen,
        "title": course_title_for(chosen, titles_index) or chosen,
        "category": "Educational Enrichment",
        "units": units,
        "reason": f"Enrichment: {track}",
    }

    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for r in prev_recs:
        if not isinstance(r, dict):
            continue
        c = _norm(r.get("course"))
        if c and c not in seen:
            merged.append(r)
            seen.add(c)
    c_new = _norm(chosen)
    if c_new not in seen:
        merged.append(new_item)
        seen.add(c_new)

    total_units = sum(int((r or {}).get("units") or 0) for r in merged if isinstance(r, dict))
    return {
        "recommended": merged,
        "total_units": total_units,
        "advice": f"Added {chosen} for Educational Enrichment ({track}). Total: {total_units} units.",
        "assistant_reply": (
            f"Yes, I added {chosen} for your Educational Enrichment ({track}). "
            f"I kept your other courses the same. Total {total_units} units."
        ),
    }


def resolve_enrichment_subjects_for_slot(
    user_preference: str,
) -> tuple[list[str], str, str | None]:
    """Pick subjects + UI labels for slot popover.

    Returns:
        (subjects, track_label, prompt_or_none)
    """
    subjects = infer_enrichment_subjects(user_preference)
    if subjects:
        return subjects, enrichment_track_label(subjects), None

    return (
        [],
        "",
        "Describe your enrichment track in chat (e.g. art, history, HIST).",
    )
