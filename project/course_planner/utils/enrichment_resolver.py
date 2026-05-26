"""Educational Enrichment (major): department-sequence course resolution.

Unlike Core/GE open requirements (Course Tags in the schedule xlsx), enrichment
for COEN/CSE-style programs is typically "three courses in the same department"
(e.g. three CHIN courses). Students describe direction in natural language
("中文", "Chinese") rather than a specific catalog code.

This module is deterministic (no LLM). Planning and slot-suggestion endpoints
call it to list next-term candidates.
"""

from __future__ import annotations

import re
from typing import Any

EDUCATIONAL_ENRICHMENT_MARKER = "educational enrichment"

# Title substrings that indicate a Chinese-language / China-studies course when
# the department prefix alone is not enough.
_CHINESE_TITLE_HINTS = (
    "chinese",
    "china",
    "sino",
    "mandarin",
    "cantonese",
    "中文",
    "汉语",
    "国语",
)

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
    """Infer department prefix(es) from free-form text (e.g. 中文 → CHIN)."""
    text = (user_preference or "").strip()
    if not text:
        return []
    u = text.upper()
    out: list[str] = []
    seen: set[str] = set()

    for m in re.finditer(r"\b([A-Za-z]{2,6})\b", text):
        raw = m.group(1)
        subj = raw.upper()
        if raw != subj and subj != "CHIN":
            continue
        if re.match(r"\s*\d", text[m.end():]):
            continue
        if subj.isalpha() and 2 <= len(subj) <= 6 and subj not in seen:
            out.append(subj)
            seen.add(subj)

    if (
        any(tok in text for tok in ("中文", "汉语", "国语", "中国人", "华裔"))
        or "CHINESE" in u
    ):
        if "CHIN" not in seen:
            out.insert(0, "CHIN")
            seen.add("CHIN")

    return out[:3]


def enrichment_track_label(subjects: list[str]) -> str:
    """Human-facing label for the active enrichment direction."""
    if not subjects:
        return ""
    if subjects == ["CHIN"] or (len(subjects) == 1 and subjects[0] == "CHIN"):
        return "Chinese (CHIN)"
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
    """True if *course_code* fits the enrichment direction.

    For CHIN track: prefix CHIN **or** title contains Chinese-related keywords.
    For other explicit subjects: match department prefix only.
    """
    if not subjects:
        return False
    parts = _split_course_code(course_code)
    if not parts:
        return False
    subj, _num = parts
    title_l = (title or "").lower()

    for want in subjects:
        if subj == want:
            return True
        if want == "CHIN":
            if any(h in title_l for h in _CHINESE_TITLE_HINTS):
                return True
    return False


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


_ADVANCED_CHINESE_HINTS = (
    "高阶",
    "母语",
    "native speaker",
    "native chinese",
    "中国人",
    "华裔",
    "advanced chinese",
)


def wants_advanced_chinese_only(user_preference: str) -> bool:
    """True when the student says they cannot take low-level Chinese courses."""
    text = (user_preference or "").strip()
    if not text:
        return False
    lower = text.lower()
    if any(h in text for h in ("高阶", "母语", "中国人", "华裔")):
        return True
    return any(h in lower for h in ("native speaker", "native chinese", "advanced chinese"))


def is_low_level_chin_course(course_code: str) -> bool:
    """Intro/elementary CHIN — typically inappropriate for native speakers."""
    code = " ".join(str(course_code).split()).upper()
    if not code.startswith("CHIN "):
        return False
    m = re.match(r"^CHIN\s+(\d+)([A-Z]?)$", code)
    if not m:
        return False
    num = int(m.group(1))
    # CHIN 1–2 and 11A-style lower division
    return num <= 2 or num == 11


def filter_enrichment_codes_for_preference(
    codes: list[str],
    user_preference: str,
) -> list[str]:
    if not wants_advanced_chinese_only(user_preference):
        return codes
    return [c for c in codes if not is_low_level_chin_course(c)]


def implicit_removal_codes_for_followup(
    user_preference: str,
    previous_plan: dict[str, Any] | None,
) -> set[str]:
    """Courses to drop on follow-up without the student naming a code.

    Native/advanced Chinese speakers cannot take CHIN 1-style courses; if one
    is already on the plan, remove it when they say so in natural language.
    """
    if not wants_advanced_chinese_only(user_preference):
        return set()
    prev = (previous_plan or {}).get("recommended") or []
    out: set[str] = set()
    for row in prev:
        if not isinstance(row, dict):
            continue
        code = " ".join(str(row.get("course") or "").split()).upper()
        if code and is_low_level_chin_course(code):
            out.add(code)
    return out


def should_show_slot_enrichment(
    user_preference: str,
    missing_details: list[dict[str, Any]] | None,
    *,
    plan_course_codes: list[str] | None = None,
) -> bool:
    """Whether the slot popover should show the Enrichment section.

    Still show after CHIN 1 is on the calendar — the transcript gap row may
    disappear even though the student is still building a 3-course CHIN track.
    """
    if has_educational_enrichment_gap(missing_details):
        return True
    if user_mentions_enrichment(user_preference):
        return True
    if infer_enrichment_subjects(user_preference):
        return True
    for code in plan_course_codes or []:
        if " ".join(str(code).split()).upper().startswith("CHIN "):
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
    enrich_codes = filter_enrichment_codes_for_preference(
        enrich_codes, user_preference
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
    *,
    default_chinese_when_unspecified: bool = True,
) -> tuple[list[str], str, str | None]:
    """Pick subjects + UI labels for slot popover.

    Returns:
        (subjects, track_label, prompt_or_none)
    """
    subjects = infer_enrichment_subjects(user_preference)
    if subjects:
        return subjects, enrichment_track_label(subjects), None

    if default_chinese_when_unspecified:
        return (
            ["CHIN"],
            "Chinese (CHIN)",
            "Describe your enrichment track in chat (e.g. art, history); below defaults to the Chinese series.",
        )

    return [], "", "Describe your enrichment track in chat (e.g. Chinese)."
