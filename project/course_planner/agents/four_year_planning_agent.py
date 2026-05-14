from __future__ import annotations

import json
import os
import re
import time
import uuid
from datetime import date
from typing import Any

from google.genai import types

from agents.gemini_client import get_genai_client
from agents.planning_agent import _normalize_open_req_text, _resolve_item_codes, _resolve_open_requirement
from utils.scu_course_schedule_xlsx import load_category_course_index, load_schedule_section_index, planned_section_keys

DEFAULT_MODEL = "gemini-2.5-flash"
FALLBACK_MODELS = ("gemini-2.5-flash-lite", "gemini-1.5-flash")

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

    open_req_courses: dict[str, list[str]] = {}  # course → list of requirement labels it satisfies
    for item in missing_details:
        # Skip if the extracted code has a real SCU subject prefix — that
        # means it's a specific course requirement (even if next-term not
        # offering it like CSEN 195). "Core: ENGR: RTC 3" extracts "RTC 3"
        # but RTC isn't a real subject, so it falls through to open-req.
        codes = _resolve_item_codes(item)
        if codes and any(c.split()[0] in real_subjects for c in codes):
            continue
        req_text = (item.get("requirement") or item.get("category") or "")
        candidates = _resolve_open_requirement(req_text, category_index, schedule_index)
        if not candidates:
            continue
        label = _normalize_open_req_text(req_text) or req_text[:40]
        for c in candidates:
            open_req_courses.setdefault(c, []).append(label)

    open_req_block = ""
    if open_req_courses:
        lines = [
            "=== COURSES SATISFYING OPEN CORE/GE REQUIREMENTS ===",
            "The remaining requirements above include open Core/GE categories",
            "(RTC 3, ELSJ, Advanced Writing, Arts, etc.) that have no specific",
            "course code. The following courses are CONFIRMED to satisfy them",
            "and ARE available in next-term schedule. You MUST pick courses",
            "from this list — do NOT invent placeholder names like",
            "'Core - RTC 3' or 'Open Elective'.",
            "★ marks courses that satisfy MULTIPLE requirements simultaneously",
            "(double-tagged) — prefer these to graduate faster.",
        ]
        # Sort by # of requirements (double-tagged first)
        sorted_courses = sorted(
            open_req_courses.items(),
            key=lambda kv: (-len(kv[1]), kv[0]),
        )
        for course, labels in sorted_courses:
            tag = " ★" if len(labels) > 1 else ""
            joined = " + ".join(labels)
            lines.append(f"  {course} (satisfies: {joined}){tag}")
        open_req_block = "\n".join(lines) + "\n\n"

    pref_block = f"\nStudent preferences / constraints:\n{preferences.strip()}\n" if preferences and preferences.strip() else ""

    prompt = f"""You are an SCU academic advisor building a MULTI-QUARTER graduation plan.

TODAY: {date.today().isoformat()} — SCU uses Fall / Winter / Spring quarters.

NEXT TERMS (in order): {", ".join(term_list)}

REMAINING REQUIREMENTS ({len(missing_details)} courses, {total_units} total units):
{json.dumps(missing_details, ensure_ascii=False, indent=2)}

{open_req_block}{pref_block}
RULES:
1. Distribute ALL courses above across as many quarters as needed, INCLUDING
   every open Core/GE requirement. For each open requirement, pick ONE
   concrete course from the "COURSES SATISFYING OPEN CORE/GE REQUIREMENTS"
   block above and place it in some quarter. Never leave a Core requirement
   unscheduled, and never emit a placeholder name like "Core - RTC 3".
2. PREFER double-tagged courses (marked with ★) — picking one such course
   resolves several open requirements at once and shortens the plan.
3. Target 12–16 units per quarter; never exceed 20.
4. Respect typical prerequisites: introductory/numbered-lower courses before advanced ones.
5. Group lecture + lab pairs (e.g. CSEN 194 + CSEN 194L) in the SAME quarter.
6. If a course is only offered in certain quarters (Fall/Spring), note that in reason.
7. Each course must appear in EXACTLY ONE quarter — no duplicates, no omissions.
8. Use only the term names from the NEXT TERMS list above.
9. graduation_term = the last term in your plan.
10. total_remaining_units must be the sum of `units` across all courses you output.
11. advice: 1-3 sentence overview of the plan strategy (max 400 chars).
12. reason per course: ≤60 chars, explain why it belongs in that quarter.

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

    # ────────────────────────────────────────────────────────────────────────
    parsed.setdefault("total_remaining_units", total_units)
    parsed["meta"] = {"provider": "gemini", "model": candidate, "request_id": request_id}
    return parsed
