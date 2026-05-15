from __future__ import annotations

import hashlib
import json
import os
import re
import time
import uuid
from collections import OrderedDict
from datetime import date
from threading import Lock
from typing import Any

from google.genai import types

from agents.gemini_client import get_genai_client
from agents.planning_agent import _normalize_open_req_text, _resolve_item_codes, _resolve_open_requirement
from utils.scu_course_schedule_xlsx import (
    course_title_for,
    load_category_course_index,
    load_course_titles_index,
    load_schedule_section_index,
    planned_section_keys,
)

DEFAULT_MODEL = "gemini-2.5-flash"
FALLBACK_MODELS = ("gemini-2.5-flash-lite", "gemini-1.5-flash")

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


def _is_transient(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "503" in msg or "unavailable" in msg or "high demand" in msg


def run_four_year_plan_agent(
    missing_details: list[dict],
    preferences: str | None = None,
) -> dict[str, Any]:
    """
    Generate a multi-quarter graduation plan from all remaining requirements.

    Returns a dict with keys: quarters, graduation_term, total_remaining_units, advice.
    Each quarter has: term (str), courses (list), total_units (int).
    """
    if not missing_details:
        return {
            "quarters": [],
            "graduation_term": "Unknown",
            "total_remaining_units": 0,
            "advice": "No remaining requirements found.",
        }

    start_q, start_year = _next_starting_term()
    # Give the model up to 16 terms to work with (4 academic years)
    term_list = _generate_term_sequence(start_q, start_year, 16)

    total_units = sum(
        int(item.get("units") or 0)
        for item in missing_details
        if isinstance(item.get("units"), (int, float, str))
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

    prompt = f"""You are an SCU academic advisor building a MULTI-QUARTER graduation plan.

TODAY: {date.today().isoformat()} — SCU uses Fall / Winter / Spring quarters.

NEXT TERMS (in order): {", ".join(term_list)}

REMAINING REQUIREMENTS ({len(missing_details)} courses, {total_units} total units):
{json.dumps(missing_details, ensure_ascii=False, indent=2)}

{open_req_block}{pref_block}
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
4. Target 12–16 units per quarter; never exceed 20.
5. Respect typical prerequisites: introductory/numbered-lower courses before advanced ones.
6. Group lecture + lab pairs (e.g. CSEN 194 + CSEN 194L) in the SAME quarter.
7. CSEN 194 / CSEN 195 / CSEN 196 are a 3-quarter Senior Design sequence —
   schedule them in three CONSECUTIVE quarters (one per quarter) with their
   labs, and place them late in the plan (final year).
8. If a course is only offered in certain quarters (Fall/Spring), note that in reason.
9. Each course must appear in EXACTLY ONE quarter — no duplicates, no omissions.
10. Use only the term names from the NEXT TERMS list above.
11. graduation_term = the last term in your plan.
12. total_remaining_units must be the sum of `units` across all courses you output.
13. advice: 1-3 sentence overview of the plan strategy (max 400 chars).
14. reason per course: ≤60 chars, explain why it belongs in that quarter.
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
            "Output a complete multi-quarter plan covering ALL remaining requirements. "
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

    def _is_valid_course(course_code: str) -> bool:
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

    # ── Title override: schedule xlsx is the authoritative title source ──
    titles_index = load_course_titles_index()
    if titles_index:
        for quarter in parsed.get("quarters") or []:
            for c in quarter.get("courses") or []:
                if not isinstance(c, dict):
                    continue
                code = (c.get("course") or "").strip()
                real_title = course_title_for(code, titles_index)
                if real_title:
                    c["title"] = real_title

    # ────────────────────────────────────────────────────────────────────────
    parsed.setdefault("total_remaining_units", total_units)
    parsed["meta"] = {"provider": "gemini", "model": candidate, "request_id": request_id}
    return parsed
