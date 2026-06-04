from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
import uuid
from collections import OrderedDict
from datetime import date
from threading import Lock
from typing import Any

try:
    from google.genai import types
except ModuleNotFoundError:  # pragma: no cover
    types = None  # type: ignore[assignment]

DEFAULT_MODEL = "gemini-2.5-flash"
FALLBACK_MODELS = ("gemini-2.5-flash-lite", "gemini-1.5-flash")

# 4 academic years at SCU = 12 quarters (Fall/Winter/Spring).
FOUR_YEAR_TERM_COUNT = 12

# Known SCU term name prefixes (case-insensitive). The model is given a list
# of concrete "<Season> YYYY" terms but for empty quarters we only verify the
# season prefix here.
_KNOWN_TERM_PREFIXES = ("fall", "winter", "spring", "summer")


class EmptyPlanError(ValueError):
    """The model produced no usable quarters (transient failure).

    Carries a small structured payload so the HTTP layer can shape the
    response without re-parsing the message.
    """

    def __init__(self, message: str, *, detail: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.detail = detail or {}


class InconsistentPlanError(ValueError):
    """Model output disagrees with itself (e.g. units=0 yet there's work left).

    Treated as a transient failure that the caller can retry, distinct from
    a hard model failure.
    """

    def __init__(self, message: str, *, detail: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.detail = detail or {}


# ── Idempotent in-memory LRU cache for repeat requests ────────────────────────
# Keyed by a sha256 of the canonical (missing_details, preferences) tuple.
# Best-effort only; capped at 64 entries per process.

_PLAN_CACHE_TTL_SECONDS = 300  # 5 minutes
_PLAN_CACHE_MAX_ENTRIES = 64
_plan_cache: "OrderedDict[str, tuple[float, dict[str, Any]]]" = OrderedDict()
_plan_cache_lock = Lock()


def _cache_enabled() -> bool:
    """Cache is on by default. Disable with `PLAN_CACHE_ENABLED=0`."""
    return os.environ.get("PLAN_CACHE_ENABLED", "1").strip() not in ("0", "false", "False")


def compute_plan_cache_key(
    missing_details: list[dict],
    preferences: str | None,
) -> str:
    """Deterministic sha256 hash over a canonical JSON dump of the inputs."""
    payload = {
        "missing_details": missing_details or [],
        "preferences": (preferences or "").strip(),
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def get_cached_plan(cache_key: str) -> dict[str, Any] | None:
    """Return a deep-copy of the cached plan if fresh, else None."""
    if not _cache_enabled():
        return None
    now = time.time()
    with _plan_cache_lock:
        entry = _plan_cache.get(cache_key)
        if entry is None:
            return None
        ts, value = entry
        if now - ts > _PLAN_CACHE_TTL_SECONDS:
            _plan_cache.pop(cache_key, None)
            return None
        # Refresh LRU ordering.
        _plan_cache.move_to_end(cache_key)
        # Deep-copy via JSON round-trip so callers can't mutate the cache.
        return json.loads(json.dumps(value))


def set_cached_plan(cache_key: str, plan: dict[str, Any]) -> None:
    """Store a successful plan response, evicting the oldest entry if full."""
    if not _cache_enabled():
        return
    snapshot = json.loads(json.dumps(plan))
    with _plan_cache_lock:
        _plan_cache[cache_key] = (time.time(), snapshot)
        _plan_cache.move_to_end(cache_key)
        while len(_plan_cache) > _PLAN_CACHE_MAX_ENTRIES:
            _plan_cache.popitem(last=False)


def clear_plan_cache() -> None:
    """Test helper: drop all cached plans."""
    with _plan_cache_lock:
        _plan_cache.clear()

FOUR_YEAR_PLAN_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "quarters": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "term": {"type": "STRING"},
                    "courses": {
                        "type": "ARRAY",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "course": {"type": "STRING"},
                                "title": {"type": "STRING"},
                                "category": {"type": "STRING"},
                                "units": {"type": "INTEGER"},
                                "reason": {"type": "STRING"},
                            },
                            "required": ["course", "title", "category", "units", "reason"],
                        },
                    },
                    "total_units": {"type": "INTEGER"},
                },
                "required": ["term", "courses", "total_units"],
            },
        },
        "graduation_term": {"type": "STRING"},
        "total_remaining_units": {"type": "INTEGER"},
        "advice": {"type": "STRING"},
    },
    "required": ["quarters", "graduation_term", "total_remaining_units", "advice"],
}

_QUARTER_NEXT = {"Fall": "Winter", "Winter": "Spring", "Spring": "Fall"}


def _next_starting_term() -> tuple[str, int]:
    """Return (quarter_name, calendar_year) for the next SCU quarter from today."""
    today = date.today()
    month, year = today.month, today.year
    if month <= 3:
        return "Spring", year
    if month <= 8:
        return "Fall", year
    return "Winter", year + 1


_ACAD_PERIOD_PATTERNS: tuple = (
    (re.compile(r"^(Fall|Winter|Spring)\s+(\d{4})\s+Quarter$", re.I),
     lambda m: (m.group(1).capitalize(), int(m.group(2)))),
    (re.compile(r"^(\d{4})-(\d{4})\s+(Fall|Winter|Spring)\s+Quarter$", re.I),
     lambda m: (m.group(3).capitalize(),
                int(m.group(1)) if m.group(3).lower() == "fall" else int(m.group(1)) + 1)),
    (re.compile(r"^(Fall|Winter|Spring)\s+(\d{4})-\d{4}$", re.I),
     lambda m: (m.group(1).capitalize(), int(m.group(2)))),
    (re.compile(r"^(Fall|Winter|Spring)\s+(\d{4})$", re.I),
     lambda m: (m.group(1).capitalize(), int(m.group(2)))),
)


def _parse_academic_period(period: str) -> str | None:
    """Normalize a transcript academic-period string to '<Season> YYYY'."""
    p = str(period or "").strip()
    for rx, fn in _ACAD_PERIOD_PATTERNS:
        m = rx.match(p)
        if m:
            season, year = fn(m)
            return f"{season} {year}"
    return None


def _latest_in_progress_term(parsed_rows: list[dict] | None) -> str | None:
    """Latest term the student is currently enrolled in (status 'In Progress').

    The four-year plan must start AFTER this quarter — the student's upcoming
    quarter is already scheduled, so new courses don't belong there.
    """
    best: str | None = None
    best_key: tuple[int, int] | None = None
    for r in parsed_rows or []:
        if not isinstance(r, dict):
            continue
        if "progress" not in str(r.get("status") or "").strip().lower():
            continue
        term = _parse_academic_period(str(r.get("academic_period") or ""))
        if not term:
            continue
        k = _term_sort_key(term)
        if best_key is None or k > best_key:
            best_key, best = k, term
    return best


def _generate_term_sequence(start_q: str, start_year: int, n: int) -> list[str]:
    terms, q, yr = [], start_q, start_year
    for _ in range(n):
        terms.append(f"{q} {yr}")
        if q == "Fall":
            yr += 1  # Fall→Winter crosses the calendar year
        q = _QUARTER_NEXT[q]
    return terms


def _parse_json_from_response(text: str) -> dict[str, Any]:
    text = text.strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if m:
        text = m.group(1).strip()
    return json.loads(text)

# ── Plan-length budget ───────────────────────────────────────────────────────
# Target per-quarter load. A typical full-time SCU engineering quarter is
# ~18 units: two Core/GE courses + two major courses (4 units each) plus a
# 1-unit lab. We aim for 16–18 so quarters are packed realistically instead
# of being spread thin across extra years.
_TARGET_UNITS_LOW = 16
_TARGET_UNITS_PER_QUARTER = 18
# Hard cap on per-quarter units. 20 is a fine full load at SCU; anything above
# 20 is overloading and must never be recommended.
_HARD_UNIT_CAP_PER_QUARTER = 20
# Course-count budget. A full-time SCU quarter is typically 3–4 courses; we
# default to 4 and never schedule more than 5 in one quarter. This is the
# decisive guard when Workday gap rows lack a `units` field (so the units
# budget alone would collapse the plan into one over-stuffed quarter).
_TARGET_COURSES_PER_QUARTER = 4
_MAX_COURSES_PER_QUARTER = 5

# Workday "pseudo" subject codes that are NOT real SCU courses — they are
# placeholders the Academic Progress export emits for an unfilled Core/GE
# requirement (e.g. "IDEAS 1" for the "Cultures & Ideas 1" requirement). They
# must never appear in a plan as if they were a course; instead the requirement
# is resolved to a real course via the candidate resolver.
_WORKDAY_PSEUDO_SUBJECTS = {"IDEAS"}


def _is_pseudo_course_code(code: str) -> bool:
    """True for Workday placeholder codes (e.g. 'IDEAS 1') that aren't courses."""
    parts = (code or "").strip().upper().split()
    return bool(parts) and parts[0] in _WORKDAY_PSEUDO_SUBJECTS


# Senior design sequence (CSEN/COEN 194, 195, 196 — with or without trailing L).
_SENIOR_DESIGN_RE = re.compile(
    r"\b(?:CSEN|COEN)\s*/?\s*(?:CSEN|COEN)?\s+19[456]L?\b",
    re.IGNORECASE,
)


def _has_senior_design(missing_details: list[dict]) -> bool:
    """True if any remaining requirement references CSEN/COEN 194/195/196."""
    for item in missing_details or []:
        for field in ("requirement", "category", "course"):
            val = item.get(field) if isinstance(item, dict) else None
            if isinstance(val, str) and _SENIOR_DESIGN_RE.search(val):
                return True
    return False


def _estimate_quarter_budget(
    *,
    total_units: int,
    total_courses: int = 0,
    has_senior_design: bool,
) -> dict[str, int]:
    """Compute the minimum / target / max number of quarters for the plan.

    The LLM tends to spray a small number of courses across many quarters
    when given a 12-term window. We trim that window down to (target + 1)
    so it is forced to pack quarters near the 14-unit target.

    The budget is driven by BOTH remaining units and remaining course count,
    taking whichever needs more quarters. The course-count term is essential:
    Workday gap rows frequently omit `units`, so a units-only budget would
    underestimate to ~0 and collapse the whole plan into a single quarter
    crammed with 10+ courses.
    """
    units = max(0, int(total_units or 0))
    courses = max(0, int(total_courses or 0))
    # Absolute minimum quarters from the unit cap.
    min_quarters_units = max(1, math.ceil(units / _HARD_UNIT_CAP_PER_QUARTER)) if units > 0 else 1
    # Quarters needed to hit the 14-unit target.
    target_quarters_units = max(1, math.ceil(units / _TARGET_UNITS_PER_QUARTER)) if units > 0 else 1
    # Minimum quarters from the 5-course-per-quarter hard cap.
    min_quarters_courses = (
        max(1, math.ceil(courses / _MAX_COURSES_PER_QUARTER)) if courses > 0 else 1
    )
    # Quarters needed to hit the 4-course-per-quarter target.
    target_quarters_courses = (
        max(1, math.ceil(courses / _TARGET_COURSES_PER_QUARTER)) if courses > 0 else 1
    )
    # Senior Design forces three consecutive quarters at the end of the plan.
    floor = 3 if has_senior_design else 1
    min_quarters = max(min_quarters_units, min_quarters_courses, floor)
    target_quarters = max(target_quarters_units, target_quarters_courses, floor)
    # Allow one quarter of slack so prereq ordering isn't impossible, but
    # never give the LLM the full 12-term window when far fewer are needed.
    max_quarters = min(FOUR_YEAR_TERM_COUNT, max(target_quarters + 1, min_quarters))
    return {
        "min_quarters": min_quarters,
        "target_quarters": target_quarters,
        "max_quarters": max_quarters,
    }


def _term_after(term: str) -> str:
    """Return the SCU quarter immediately after a "<Season> YYYY" term."""
    parts = str(term).split()
    if len(parts) != 2:
        return term
    season, year_s = parts[0].capitalize(), parts[1]
    try:
        year = int(year_s)
    except ValueError:
        return term
    nxt = _QUARTER_NEXT.get(season)
    if not nxt:
        return term
    if season == "Fall":  # Fall → Winter crosses the calendar year
        year += 1
    return f"{nxt} {year}"


_SEASON_RANK = {"Fall": 0, "Winter": 1, "Spring": 2, "Summer": 3}


def _term_sort_key(term: str) -> tuple[int, int]:
    """Chronological sort key for a "<Season> YYYY" term.

    SCU academic years run Fall→Winter→Spring, where Winter/Spring share the
    calendar year *after* the Fall, so Fall 2026, Winter 2027, Spring 2027 all
    belong to academic year 2026 and sort in that order.
    """
    parts = str(term).split()
    if len(parts) != 2:
        return (9999, 9)
    season = parts[0].capitalize()
    try:
        year = int(parts[1])
    except ValueError:
        return (9999, 9)
    rank = _SEASON_RANK.get(season, 9)
    acad_year = year if season == "Fall" else year - 1
    return (acad_year, rank)


def _lab_base(code: str) -> str:
    """Base code shared by a lecture and its lab (drops a trailing L)."""
    c = (code or "").strip().upper()
    return c[:-1] if c.endswith("L") else c


def _group_courses_keeping_labs(courses: list[dict]) -> list[list[dict]]:
    """Group a quarter's courses so a lecture + its lab move as one unit (R1)."""
    by_base: "OrderedDict[str, list[dict]]" = OrderedDict()
    for c in courses:
        if not isinstance(c, dict):
            continue
        base = _lab_base(str(c.get("course") or ""))
        by_base.setdefault(base, []).append(c)
    return list(by_base.values())


def _enforce_course_count_cap(
    plan: dict[str, Any],
    max_courses: int = _MAX_COURSES_PER_QUARTER,
) -> dict[str, Any]:
    """Guarantee no quarter exceeds ``max_courses`` by spilling overflow forward.

    Courses are processed in their existing order so prerequisite sequencing is
    preserved; a lecture and its lab always stay in the same quarter. When the
    final quarter overflows we append new quarters (continuing the term
    sequence). As an absolute last resort — only if we would exceed the 4-year
    window — the remainder is left in the last quarter rather than dropped,
    because dropping a required course is never acceptable.
    """
    quarters = plan.get("quarters") or []
    if not isinstance(quarters, list) or not quarters:
        return plan

    def _split_groups(groups: list[list[dict]]) -> tuple[list[list[dict]], list[list[dict]]]:
        kept: list[list[dict]] = []
        overflow: list[list[dict]] = []
        count = 0
        full = False
        for g in groups:
            if not full and count + len(g) <= max_courses:
                kept.append(g)
                count += len(g)
            else:
                full = True
                overflow.append(g)
        return kept, overflow

    def _build_quarter(term: str, groups: list[list[dict]]) -> dict[str, Any]:
        flat = [c for g in groups for c in g]
        return {
            "term": term,
            "courses": flat,
            "total_units": sum(int(c.get("units") or 0) for c in flat if isinstance(c, dict)),
        }

    new_quarters: list[dict[str, Any]] = []
    carry: list[list[dict]] = []
    for q in quarters:
        if not isinstance(q, dict):
            continue
        groups = carry + _group_courses_keeping_labs(q.get("courses") or [])
        kept, carry = _split_groups(groups)
        nq = dict(q)
        rebuilt = _build_quarter(str(q.get("term") or ""), kept)
        nq["courses"] = rebuilt["courses"]
        nq["total_units"] = rebuilt["total_units"]
        new_quarters.append(nq)

    while carry:
        if len(new_quarters) >= FOUR_YEAR_TERM_COUNT:
            # No room left in the 4-year window: keep the courses rather than
            # drop them, accepting a slightly over-full final quarter.
            leftover = [c for g in carry for c in g]
            target = new_quarters[-1]
            target["courses"] = list(target.get("courses") or []) + leftover
            target["total_units"] = sum(
                int(c.get("units") or 0) for c in target["courses"] if isinstance(c, dict)
            )
            carry = []
            break
        last_term = new_quarters[-1]["term"] if new_quarters else plan.get("graduation_term") or ""
        next_term = _term_after(str(last_term))
        kept, carry = _split_groups(carry)
        new_quarters.append(_build_quarter(next_term, kept))

    plan["quarters"] = new_quarters
    if new_quarters:
        plan["graduation_term"] = str(
            new_quarters[-1].get("term") or plan.get("graduation_term") or ""
        )
    return plan


# Sequential Core sequences taken back-to-back. The level-2 course is the SAME
# course as level 1 with the next catalog number (e.g. HIST 11A → HIST 12A),
# scheduled the immediately following quarter. SCU offers these as a locked
# fall→winter pair, and the next-quarter catalog only ever lists one of them, so
# we DERIVE level 2 from the chosen level-1 course instead of trusting the
# resolver (which otherwise leaves level 2 unfilled).
_SEQUENTIAL_CORE_SEQUENCES = (
    ("cultures and ideas 1", "cultures and ideas 2", "Cultures & Ideas"),
    ("critical thinking and writing 1", "critical thinking and writing 2",
     "Critical Thinking & Writing"),
)

_SEQ_CODE_RE = re.compile(r"\s*([A-Z]{2,6})\s+(\d{1,3})([A-Z]?)\s*$", re.IGNORECASE)


def _norm_category(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "").lower().replace("&", " and ")).strip()


def _requirement_display_label(req_text: str) -> str:
    """Human-readable name for a requirement, for a generic placeholder card.

    'Core: ENGR: University Core'                         -> 'University Core'
    'Core: ENGR: Critical Thinking & Writing 2'           -> 'Critical Thinking & Writing 2'
    '... Major: Educational Enrichment – Courses'         -> 'Educational Enrichment – Courses'
    """
    t = str(req_text or "").strip()
    if ":" in t:
        t = t.split(":")[-1].strip()
    t = re.sub(r"\s*\([^)]*\)\s*", " ", t).strip()
    return t or "Requirement"


def _distribute_placeholders(
    plan: dict[str, Any],
    placeholders: list[dict[str, Any]],
    max_courses: int = _MAX_COURSES_PER_QUARTER,
) -> dict[str, Any]:
    """Add generic requirement placeholders to the lightest quarters under cap."""
    if not placeholders:
        return plan
    quarters = plan.get("quarters") or []
    if not isinstance(quarters, list):
        quarters = []
    for ph in placeholders:
        target = None
        for q in sorted(
            quarters,
            key=lambda q: (len(q.get("courses") or []), _term_sort_key(str(q.get("term") or ""))),
        ):
            if len(q.get("courses") or []) < max_courses:
                target = q
                break
        if target is None:
            last_term = str(quarters[-1].get("term") or "") if quarters else ""
            target = {"term": _term_after(last_term), "courses": [], "total_units": 0}
            quarters.append(target)
        target["courses"] = list(target.get("courses") or []) + [ph]
        target["total_units"] = sum(
            int(c.get("units") or 0) for c in target["courses"] if isinstance(c, dict)
        )
    quarters.sort(key=lambda q: _term_sort_key(str(q.get("term") or "")))
    plan["quarters"] = quarters
    return plan


def _enforce_sequential_core_pairs(
    plan: dict[str, Any],
    missing_details: list[dict],
) -> dict[str, Any]:
    """Lock back-to-back Core sequences (Cultures & Ideas 1→2, CTW 1→2).

    When BOTH levels are still required and the model has scheduled a real
    course for level 1, the level-2 course is forced to the same subject with
    the next catalog number, placed in the quarter immediately after level 1.
    """
    quarters = plan.get("quarters") or []
    if not isinstance(quarters, list) or not quarters:
        return plan

    req_texts = [
        _norm_category(it.get("requirement") or it.get("category") or "")
        for it in (missing_details or [])
        if isinstance(it, dict)
    ]

    for l1_tag, l2_tag, label in _SEQUENTIAL_CORE_SEQUENCES:
        if not any(l2_tag in r for r in req_texts):
            continue

        # Find the scheduled level-1 course (by its category tag).
        l1_idx: int | None = None
        l1_course: dict | None = None
        for qi, q in enumerate(quarters):
            for c in q.get("courses") or []:
                if isinstance(c, dict) and l1_tag in _norm_category(c.get("category")):
                    l1_idx, l1_course = qi, c
                    break
            if l1_course is not None:
                break
        if l1_course is None:
            continue

        m = _SEQ_CODE_RE.match(str(l1_course.get("course") or ""))
        if not m:
            continue
        subj, num, suffix = m.group(1).upper(), int(m.group(2)), m.group(3).upper()
        level2_code = f"{subj} {num + 1}{suffix}"

        # Drop any existing level-2 entry the model produced (placeholder or a
        # mismatched catalog pick) so we replace it with the derived course.
        for q in quarters:
            q["courses"] = [
                c
                for c in (q.get("courses") or [])
                if not (isinstance(c, dict) and l2_tag in _norm_category(c.get("category")))
            ]

        level2 = {
            "course": level2_code,
            "title": l1_course.get("title"),
            "category": f"Core: {label} 2",
            "units": l1_course.get("units"),
            "reason": f"Back-to-back sequence with {l1_course.get('course')} (same course, next number)",
        }
        target_term = _term_after(str(quarters[l1_idx].get("term") or ""))
        target_q = next(
            (q for q in quarters if str(q.get("term") or "") == target_term), None
        )
        if target_q is None:
            target_q = {"term": target_term, "courses": [], "total_units": 0}
            quarters.append(target_q)
        target_q["courses"] = list(target_q.get("courses") or []) + [level2]

    for q in quarters:
        if isinstance(q, dict):
            q["total_units"] = sum(
                int(c.get("units") or 0)
                for c in (q.get("courses") or [])
                if isinstance(c, dict)
            )
    quarters.sort(key=lambda q: _term_sort_key(str(q.get("term") or "")))
    plan["quarters"] = quarters
    return plan


def _drop_empty_quarters(plan: dict[str, Any]) -> dict[str, Any]:
    """Remove quarters with no courses; recompute graduation_term safely."""
    quarters = plan.get("quarters") or []
    if not isinstance(quarters, list):
        return plan
    kept = []
    for q in quarters:
        if not isinstance(q, dict):
            continue
        courses = q.get("courses") or []
        if isinstance(courses, list) and len(courses) == 0:
            continue
        kept.append(q)
    plan["quarters"] = kept
    if kept:
        plan["graduation_term"] = str(kept[-1].get("term") or plan.get("graduation_term") or "")
    return plan


def _is_transient(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "503" in msg or "unavailable" in msg or "high demand" in msg


def run_four_year_plan_agent(
    missing_details: list[dict],
    preferences: str | None = None,
    parsed_rows: list[dict] | None = None,
    confirmed_major_id: str | None = None,
) -> dict[str, Any]:
    """
    Generate a multi-quarter graduation plan from all remaining requirements.

    Returns a dict with keys: quarters, graduation_term, total_remaining_units, advice.
    Each quarter has: term (str), courses (list), total_units (int).
    """
    if types is None:
        raise RuntimeError(
            "google-genai is not installed; four-year plan generation is unavailable."
        )
    # Import heavier dependencies lazily so light unit tests can import this module
    # without requiring the full runtime dependency set (openpyxl, google-genai, etc.).
    from agents.gemini_client import get_genai_client
    from agents.planning_agent import (
        ENGLISH_ONLY_USER_OUTPUT_RULE,
        _normalize_open_req_text,
        _resolve_item_codes,
        _resolve_open_requirement,
    )
    from utils.academic_progress_helpers import (
        enrich_missing_details,
        expand_partial_requirement_gaps,
        extract_completed_course_codes,
    )
    from utils.major_requirements import (
        build_major_advisor_block,
        enforce_senior_design_in_final_quarters,
        filter_superseded_missing_details,
        normalize_major_id,
        normalize_senior_design_courses,
        resolve_major_id,
    )
    from utils.scu_course_schedule_xlsx import (
        course_title_for,
        course_units_for,
        load_category_course_index,
        load_course_titles_index,
        load_course_units_index,
        load_schedule_section_index,
        planned_section_keys,
    )
    if not missing_details:
        return {
            "quarters": [],
            "graduation_term": "Unknown",
            "total_remaining_units": 0,
            "advice": "No remaining requirements found.",
        }

    completed_set = extract_completed_course_codes(parsed_rows)
    major_for_filter = normalize_major_id(
        resolve_major_id(
            confirmed_major_id=confirmed_major_id,
            missing_details=missing_details,
            parsed_rows=parsed_rows,
        )
    )
    missing_details, superseded_advice_notes = filter_superseded_missing_details(
        missing_details, completed_set, major_id=major_for_filter
    )
    missing_details = expand_partial_requirement_gaps(missing_details, parsed_rows)
    if not missing_details:
        advice = "No remaining requirements need to be scheduled."
        if superseded_advice_notes:
            advice = f"{advice} {' '.join(superseded_advice_notes)}"
        return {
            "quarters": [],
            "graduation_term": "Unknown",
            "total_remaining_units": 0,
            "advice": advice[:900],
        }

    start_q, start_year = _next_starting_term()

    # If the student is already enrolled in an upcoming quarter (status "In
    # Progress"), begin the plan the quarter AFTER it — that quarter is already
    # full, so new courses must not be piled on top of the current enrollment.
    in_progress_term = _latest_in_progress_term(parsed_rows)
    if in_progress_term:
        after_ip = _term_after(in_progress_term)
        if _term_sort_key(after_ip) > _term_sort_key(f"{start_q} {start_year}"):
            _parts = after_ip.split()
            start_q, start_year = _parts[0], int(_parts[1])

    # Workday gap rows frequently omit `units`. Enrich a copy (lecture/lab
    # defaults + transcript lookups) so the unit budget below isn't computed
    # from a near-zero total that would collapse the plan into one quarter.
    enriched_details = enrich_missing_details(missing_details, parsed_rows)
    total_units = sum(
        int(item.get("units") or 0)
        for item in enriched_details
        if isinstance(item.get("units"), (int, float, str))
    )
    total_courses = len(missing_details)

    # Workday emits placeholder "course" codes (e.g. "IDEAS 1") for unfilled
    # Core/GE requirements. Null those out for the prompt so the model fills the
    # requirement from the real candidate list instead of echoing the fake code.
    prompt_details: list[dict] = []
    for item in missing_details:
        if isinstance(item, dict) and _is_pseudo_course_code(str(item.get("course") or "")):
            cleaned = dict(item)
            cleaned["course"] = None
            prompt_details.append(cleaned)
        else:
            prompt_details.append(item)

    # Trim the candidate term list to a tight budget derived from BOTH the
    # remaining units and the remaining course count. Giving the model 12
    # terms when only ~3 are needed leads it to spread courses one-per-quarter
    # across many years; conversely, a units-only budget collapses to one
    # over-stuffed quarter when units are missing. We give it (target+1) terms
    # so it packs near 14 units / 4 courses per quarter.
    has_senior_design = _has_senior_design(missing_details)
    budget = _estimate_quarter_budget(
        total_units=total_units,
        total_courses=total_courses,
        has_senior_design=has_senior_design,
    )
    term_list = _generate_term_sequence(
        start_q, start_year, budget["max_quarters"]
    )

    # Build a candidate-course block for OPEN Core/GE requirements that have
    # no explicit course code in the Workday transcript (e.g. "Core: ENGR:
    # RTC 3", "Core: ENGR: Experiential Learning for Social Justice"). Each
    # candidate course can satisfy that requirement, and double-tagged courses
    # are marked with ★ so the LLM preferentially picks them.
    category_index = load_category_course_index()
    schedule_index = load_schedule_section_index()

    # Real SCU course subject prefixes (CSEN, COEN, MATH, ENGL, ...) seen
    # in the schedule xlsx — used to distinguish actual course requirements
    # ("CSEN/COEN 195/L") from category-tag-shaped strings ("RTC 3", "ELSJ").
    real_subjects = {subj for (subj, _) in schedule_index.keys()}

    # Two parallel maps:
    #   open_req_by_label   :  requirement-label → [candidate course codes]
    #   open_req_courses    :  course code → list of requirement labels it covers
    # The first drives the prompt block (grouped by requirement); the second
    # is fed to the hallucination whitelist later.
    open_req_by_label: dict[str, list[str]] = {}
    open_req_courses: dict[str, list[str]] = {}
    for item in missing_details:
        codes = _resolve_item_codes(item)
        if codes and any(c.split()[0] in real_subjects for c in codes):
            continue
        req_text = (item.get("requirement") or item.get("category") or "")
        candidates = _resolve_open_requirement(req_text, category_index, schedule_index)
        if not candidates:
            continue
        label = _normalize_open_req_text(req_text) or req_text[:40]
        open_req_by_label[label] = candidates
        for c in candidates:
            open_req_courses.setdefault(c, []).append(label)

    # Find double-tagged courses (satisfy >= 2 open requirements).
    double_tagged = sorted(
        ((c, labels) for c, labels in open_req_courses.items() if len(labels) > 1),
        key=lambda kv: (-len(kv[1]), kv[0]),
    )

    open_req_block = ""
    if open_req_by_label:
        lines = [
            "=== CANDIDATE COURSES FOR OPEN CORE/GE REQUIREMENTS ===",
            "Some items in REMAINING REQUIREMENTS above have no specific course",
            "code (e.g. 'Core: ENGR: RTC 3', 'Core: ENGR: Advanced Writing').",
            "For EACH such open requirement, you MUST pick exactly ONE course",
            "from its candidate list below and schedule it like any other course.",
            "These candidates are IN ADDITION TO — not a replacement for — the",
            "specific major / lab courses already listed in REMAINING REQUIREMENTS",
            "(e.g. CSEN 122, CSEN 194/L, ECEN 153/L). NEVER drop those.",
            "",
        ]
        if double_tagged:
            lines.append("★ DOUBLE-TAGGED (cover multiple open requirements at once — prefer these):")
            for course, labels in double_tagged[:8]:
                lines.append(f"  {course}  →  {' + '.join(labels)}")
            lines.append("")
        # Per-requirement candidate lists, capped to keep the prompt compact.
        lines.append("Per-requirement candidates (pick ONE per requirement):")
        for label, candidates in open_req_by_label.items():
            shown = candidates[:6]
            extra = f"  (… {len(candidates) - len(shown)} more)" if len(candidates) > len(shown) else ""
            lines.append(f"  • {label}: {', '.join(shown)}{extra}")
        open_req_block = "\n".join(lines) + "\n\n"

    pref_block = f"\nStudent preferences / constraints:\n{preferences.strip()}\n" if preferences and preferences.strip() else ""

    major_block, detected_major = build_major_advisor_block(
        missing_details=missing_details,
        parsed_rows=parsed_rows,
        completed=completed_set,
        confirmed_major_id=confirmed_major_id,
    )

    prompt = f"""You are an SCU academic advisor building a MULTI-QUARTER graduation plan.

TODAY: {date.today().isoformat()} — SCU uses Fall / Winter / Spring quarters.

NEXT TERMS (in order): {", ".join(term_list)}

PLAN-LENGTH BUDGET (HARD):
- Remaining work:       {total_units} units across {len(missing_details)} requirements.
- Use AT MOST           {budget['max_quarters']} quarters total.
- Target                {budget['target_quarters']} quarters at ~{_TARGET_UNITS_PER_QUARTER} units each.
- Per quarter:          schedule 3–4 courses (4 is the default full-time load);
                        NEVER more than {_MAX_COURSES_PER_QUARTER} courses in any quarter.
- Senior design present? {"YES" if has_senior_design else "no"} (forces 3 consecutive quarters).
- Picking more quarters than {budget['max_quarters']} is a critical failure —
  you MUST pack courses into fewer quarters instead of spreading them out.
- Putting more than {_MAX_COURSES_PER_QUARTER} courses in one quarter is ALSO a
  critical failure — add a quarter instead of overloading one. A lecture and
  its lab (e.g. CSEN 20 + CSEN 20L) together count as one of those courses.

REMAINING REQUIREMENTS ({len(missing_details)} courses, {total_units} total units):
{json.dumps(prompt_details, ensure_ascii=False, indent=2)}

{open_req_block}{major_block}{pref_block}
RULES:
1. The plan MUST cover EVERY item in REMAINING REQUIREMENTS — both the
   specific major / lab courses (CSEN 122, CSEN 194/L, CSEN 195/L,
   CSEN 196/L, ECEN 153/L, etc.) AND the open Core/GE categories.
   Dropping any major requirement is a critical failure.
2. For each OPEN Core/GE item (no specific code), pick exactly ONE
   concrete course from its candidate list in the CANDIDATE COURSES block
   below. If a course is double-tagged (★), prefer it because one slot
   then covers multiple open requirements.
3. Never emit placeholder names like "Core - RTC 3", "Open Elective", or
   "Educational Enrichment" — use a real course code.
4. Target {_TARGET_UNITS_LOW}–{_TARGET_UNITS_PER_QUARTER} units per quarter
   (a typical full-time engineering quarter is ~{_TARGET_UNITS_PER_QUARTER}:
   two Core/GE + two major courses + a lab); never exceed 20. Aim for 3–4
   courses per quarter (4 is the default full-time load) and NEVER more than
   {_MAX_COURSES_PER_QUARTER}. Quarters with only 1 course are NOT acceptable
   unless there is literally nothing else left to schedule in that quarter
   (e.g. the last quarter has a single lab pair). Balance the load across
   quarters rather than front-loading one quarter.
4b. Use the MINIMUM number of quarters possible WITHOUT exceeding
    {_MAX_COURSES_PER_QUARTER} courses (or {_HARD_UNIT_CAP_PER_QUARTER} units) in any single quarter.
    NEVER include empty quarters. Never spread N courses across more than
    N quarters; aim for about ⌈N/4⌉ quarters unless prereqs or term-offering
    rules force more.
5. Respect typical prerequisites: introductory/numbered-lower courses before advanced ones.
6. Group lecture + lab pairs in the SAME quarter when the requirement includes a
   lab (e.g. CSEN 194 + CSEN 194L). CSEN/COEN 195 and 196 do NOT have lab
   sections — schedule only the lecture, each as 2 units (not 4).
7. CSEN/COEN/ECEN 194 / 195 / 196 are a 3-quarter Senior Design sequence taken
   ONLY in the senior (final) year, one per quarter and locked to the term:
   194 in FALL (1 unit + 194L 1 unit), 195 in WINTER (2 units), 196 in SPRING
   (2 units) — never two in the same quarter.
   Senior Design runs CONCURRENT with other remaining major / Core courses
   (typical senior quarter: "CSEN 19x[/L] + 1–2 other courses").
7b. SEQUENTIAL CORE PAIRS — "Cultures & Ideas 1 → 2" and "Critical Thinking &
   Writing 1 → 2" are the SAME course taken back-to-back: level 2 is the same
   subject as level 1 with the next catalog number (e.g. HIST 11A → HIST 12A),
   scheduled the very next quarter (level 1 in Fall, level 2 in Winter). Pick a
   real course for level 1 from its candidate list; derive level 2 from it.
7c. EDUCATIONAL ENRICHMENT — schedule THREE separate enrichment courses (same
   department sequence, e.g. three HIST or three SOCI). Label category
   "Educational Enrichment". They are interchangeable — note in `reason`/`advice`
   that the student can swap for another enrichment course if one isn't offered.
7e. UD EMPHASIS — when REMAINING lists "3 UD Courses" slots still open, schedule
   each as a distinct upper-division CSEN/COEN/ECEN emphasis course (with lab if
   required), spread across quarters before senior year when possible.
7d. RTC (Religion, Theology & Culture) — RTC 1 must come BEFORE RTC 2 and RTC 3.
   RTC 2 and RTC 3 may be taken in either order (RTC 3 before RTC 2 is allowed).
8. If a course is only offered in certain quarters (Fall/Spring), note that in reason.
9. Each course must appear in EXACTLY ONE quarter — no duplicates, no omissions.
10. Use only the term names from the NEXT TERMS list above.
11. graduation_term = the last term in your plan.
12. total_remaining_units must be the sum of `units` across all courses you output.
13. advice: 1-3 sentence overview of the plan strategy in English (max 400 chars).
14. reason per course: ≤60 chars in English, explain why it belongs in that quarter.
15. category field MUST identify which requirement the course satisfies.
    For courses pulled from the open-Core candidate list, use the SPECIFIC
    requirement name, e.g.:
      • "Core: RTC 3"          (for SCTR 128, THTR 110, ...)
      • "Core: ELSJ"           (for ANTH 3, CHST 106, ...)
      • "Core: Advanced Writing" (for COMM 130, ENGL 101, ...)
      • "Core: Arts"
    Never use the bare label "Core" — the student must be able to see
    which specific Core requirement each course is checking off.

Output JSON matching the schema exactly.
"""

    model = os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)
    config = types.GenerateContentConfig(
        max_output_tokens=32768,
        response_mime_type="application/json",
        response_schema=FOUR_YEAR_PLAN_SCHEMA,
        system_instruction=(
            "You are an SCU graduation planner. "
            + ENGLISH_ONLY_USER_OUTPUT_RULE
            + "Output a complete multi-quarter plan covering ALL remaining requirements. "
            "Never omit a course. Never exceed 20 units per quarter. "
            "Output only valid JSON matching the schema — no extra text."
        ),
    )

    client = get_genai_client(purpose="four-year plan generation")
    request_id = str(uuid.uuid4())
    response = None
    errors: list[str] = []

    candidates = list(dict.fromkeys([model, *FALLBACK_MODELS]))
    for candidate in candidates:
        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    model=candidate,
                    contents=prompt,
                    config=config,
                )
                break
            except Exception as e:
                errors.append(f"{candidate} attempt {attempt + 1}: {e}")
                if not _is_transient(e) or attempt == 2:
                    break
                time.sleep(1.5 * (2**attempt))
        if response is not None:
            break

    if response is None:
        raise ValueError(
            "Four-year plan generation failed. " + " | ".join(errors[-3:])
        )

    text = (response.text or "").strip()
    if not text:
        raise ValueError("Model returned no content for four-year plan.")

    try:
        parsed = _parse_json_from_response(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Could not parse four-year plan JSON: {e}") from e

    # ── Hallucination filter ─────────────────────────────────────────────────
    # The four-year plan must ONLY distribute courses that are in missing_details.
    # Build a whitelist of normalised codes from the input requirements.
    # NOTE: For Workday transcripts, item["course"] is often None — codes are
    # embedded in the "requirement" or "category" text (e.g. "CSEN/COEN 122 &
    # 122L").  We therefore also extract codes from those text fields via regex.

    def _extract_codes_from_text(text: str) -> set[str]:
        """Extract all course codes from a free-form requirement string."""
        codes: set[str] = set()
        text = text.strip().upper()

        # Handle slash-subject groups: "CSEN/COEN 122" → both subjects
        for m in re.finditer(
            r"([A-Z]{2,6}(?:/[A-Z]{2,6})+)\s+(\d{1,3}[A-Z]?)", text
        ):
            subjects = m.group(1).split("/")
            number = m.group(2)
            for subj in subjects:
                codes.add(f"{subj} {number}")
        # Handle "& 122L" continuations after a slash-group match
        # e.g. "CSEN/COEN 122 & 122L" — pick up the bare number after &
        for m in re.finditer(
            r"([A-Z]{2,6}(?:/[A-Z]{2,6})+)\s+(\d{1,3}[A-Z]?)(?:\s*&\s*(\d{1,3}[A-Z]?))?",
            text,
        ):
            subjects = m.group(1).split("/")
            for number in filter(None, [m.group(2), m.group(3)]):
                for subj in subjects:
                    codes.add(f"{subj} {number}")

        # Handle simple pairs: "CSEN 140L"
        for m in re.finditer(r"\b([A-Z]{2,6})\s+(\d{1,3}[A-Z]?)\b", text):
            codes.add(f"{m.group(1)} {m.group(2)}")

        # For every code, also add the lab/non-lab variant
        extra: set[str] = set()
        for code in list(codes):
            if code.endswith("L"):
                extra.add(code[:-1])
            else:
                extra.add(code + "L")
        codes |= extra

        # CSEN ↔ COEN aliases
        alias: set[str] = set()
        for code in list(codes):
            if code.startswith("CSEN "):
                alias.add("COEN " + code[5:])
            elif code.startswith("COEN "):
                alias.add("CSEN " + code[5:])
        codes |= alias

        return codes

    required_codes: set[str] = set()
    # First pass: explicit "course" field (sometimes populated)
    for item in missing_details:
        raw = str(item.get("course") or "").strip().upper()
        if raw:
            required_codes.add(raw)
    # Second pass: extract from text fields for Workday-style requirements
    for item in missing_details:
        for field in ("requirement", "category", "course"):
            val = item.get(field)
            if val and isinstance(val, str):
                required_codes |= _extract_codes_from_text(val)
    # Third pass: every concrete course we surfaced as an open-requirement
    # candidate (e.g. SCTR 128 for RTC 3, ENGL 181 for Arts) is valid.
    for course in open_req_courses:
        required_codes.add(course.upper())
    # Drop Workday placeholder codes (e.g. "IDEAS 1") so they can never be
    # whitelisted — the real Cultures & Ideas course comes from the resolver.
    required_codes = {c for c in required_codes if not _is_pseudo_course_code(c)}

    def _is_valid_course(course_code: str) -> bool:
        # Workday placeholder codes (e.g. "IDEAS 1") are never a real course.
        if _is_pseudo_course_code(course_code):
            return False
        # If we couldn't identify any specific codes (e.g. all open-ended
        # requirements like "RTC 3"), skip the filter entirely.
        if not required_codes:
            return True
        code = (course_code or "").strip().upper()
        if not code:
            return False
        if code in required_codes:
            return True
        # Accept lab variants: e.g. "CSEN 194L" when requirement is "CSEN 194"
        # and vice-versa (strip trailing L or add it).
        if code.endswith("L") and code[:-1] in required_codes:
            return True
        if code + "L" in required_codes:
            return True
        # CSEN ↔ COEN aliases
        if code.startswith("CSEN ") and ("COEN " + code[5:]) in required_codes:
            return True
        if code.startswith("COEN ") and ("CSEN " + code[5:]) in required_codes:
            return True
        return False

    for quarter in parsed.get("quarters") or []:
        original = quarter.get("courses") or []
        filtered = [c for c in original if _is_valid_course(str(c.get("course") or ""))]
        if len(filtered) < len(original):
            removed = [str(c.get("course", "?")) for c in original if c not in filtered]
            import warnings
            warnings.warn(
                f"[four_year_plan] Hallucinated courses removed from {quarter.get('term', '?')}: "
                + ", ".join(removed),
                stacklevel=2,
            )
        quarter["courses"] = filtered
        quarter["total_units"] = sum(int(c.get("units") or 0) for c in filtered)

    # Drop empty quarters (the UI renders all returned terms).
    parsed = _drop_empty_quarters(parsed)
    if len(parsed.get("quarters") or []) > FOUR_YEAR_TERM_COUNT:
        raise InconsistentPlanError(
            f"Plan exceeds 4 academic years ({FOUR_YEAR_TERM_COUNT} quarters).",
            detail={"quarters": len(parsed.get("quarters") or [])},
        )

    # ── Title + units override: schedule xlsx is authoritative for both ──
    titles_index = load_course_titles_index()
    units_index = load_course_units_index()
    if titles_index or units_index:
        for quarter in parsed.get("quarters") or []:
            for c in quarter.get("courses") or []:
                if not isinstance(c, dict):
                    continue
                code = (c.get("course") or "").strip()
                if titles_index:
                    real_title = course_title_for(code, titles_index)
                    if real_title:
                        c["title"] = real_title
                if units_index:
                    real_units = course_units_for(code, units_index)
                    if real_units is not None:
                        c["units"] = real_units
            # recompute the quarter total after unit overrides
            if units_index:
                quarter["total_units"] = sum(
                    int(c.get("units") or 0) for c in (quarter.get("courses") or [])
                )

    # Lock back-to-back Core sequences (Cultures & Ideas 1→2, CTW 1→2): the
    # second course is the same course as the first with the next catalog
    # number, in the following quarter. Done before the cap so the derived
    # course participates in load balancing.
    parsed = _enforce_sequential_core_pairs(parsed, missing_details)

    # Any required item that still has no real course scheduled (e.g.
    # "University Core", "Religious Studies", "Critical Thinking & Writing 2"
    # that aren't offered/tagged next quarter) gets a clearly-labeled generic
    # placeholder card instead of being silently dropped — so the plan shows
    # the student exactly what's left and Remaining matches Scheduled.
    scheduled_codes: set[str] = set()
    scheduled_cats: list[str] = []
    for q in parsed.get("quarters") or []:
        for c in q.get("courses") or []:
            if isinstance(c, dict):
                scheduled_codes.add(str(c.get("course") or "").strip().upper())
                scheduled_cats.append(_norm_category(c.get("category")))
    placeholders: list[dict[str, Any]] = []
    seen_labels: set[str] = set()
    for item in missing_details:
        if not isinstance(item, dict):
            continue
        req_text = str(item.get("requirement") or item.get("category") or "")
        label = _normalize_open_req_text(req_text)
        norm_codes = {c.strip().upper() for c in _resolve_item_codes(item) if c}
        candidates = {c.upper() for c in open_req_by_label.get(label, [])}
        covered = bool(norm_codes & scheduled_codes) or bool(candidates & scheduled_codes)
        if not covered and label:
            covered = any(label in cat or (cat and cat in label) for cat in scheduled_cats)
        if covered or not req_text:
            continue
        disp = _requirement_display_label(req_text)
        if disp.lower() in seen_labels:
            continue
        seen_labels.add(disp.lower())
        units = int(item.get("units") or 0) or 4
        placeholders.append(
            {
                "course": disp,
                "title": f"{disp} (choose a course)",
                "category": disp,
                "units": units,
                "reason": "Requirement still open — pick any course that satisfies it.",
                "placeholder": True,
            }
        )
    parsed = _distribute_placeholders(parsed, placeholders)

    # Enforce the per-quarter course cap deterministically: spill any
    # overflow forward so no quarter holds more than 5 courses, regardless of
    # what the model returned. Runs before Senior Design pinning so that the
    # final-three-quarter placement has the last word on the tail of the plan.
    parsed = _enforce_course_count_cap(parsed)

    # Pin Senior Design to final three quarters for engineering majors.
    major_id = normalize_major_id(
        detected_major
        or resolve_major_id(
            confirmed_major_id=confirmed_major_id,
            missing_details=missing_details,
            parsed_rows=parsed_rows,
        )
    )
    parsed = enforce_senior_design_in_final_quarters(
        parsed, major_id, completed=completed_set
    )
    parsed = normalize_senior_design_courses(parsed, major_id)

    # ────────────────────────────────────────────────────────────────────────
    # "Remaining" must reflect the authoritative requirement total from the
    # Academic Progress report, NOT the model's self-reported number (which is
    # often inconsistent). The UI compares this against the sum of scheduled
    # quarter units; a gap means a requirement could not be placed.
    parsed["total_remaining_units"] = total_units
    if superseded_advice_notes:
        base = str(parsed.get("advice") or "").strip()
        extra = " ".join(superseded_advice_notes)
        parsed["advice"] = f"{base} {extra}".strip()[:900] if base else extra[:900]
    parsed["meta"] = {
        "provider": "gemini",
        "model": candidate,
        "request_id": request_id,
        "detected_major": major_id,
    }
    return parsed
