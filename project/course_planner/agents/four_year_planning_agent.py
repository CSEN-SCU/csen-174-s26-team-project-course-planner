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

    pref_block = f"\nStudent preferences / constraints:\n{preferences.strip()}\n" if preferences and preferences.strip() else ""

    prompt = f"""You are an SCU academic advisor building a MULTI-QUARTER graduation plan.

TODAY: {date.today().isoformat()} — SCU uses Fall / Winter / Spring quarters.

NEXT TERMS (in order): {", ".join(term_list)}

REMAINING REQUIREMENTS ({len(missing_details)} courses, {total_units} total units):
{json.dumps(missing_details, ensure_ascii=False, indent=2)}
{pref_block}
RULES:
1. Distribute ALL courses above across as many quarters as needed.
2. Target 12–16 units per quarter; never exceed 20.
3. Respect typical prerequisites: introductory/numbered-lower courses before advanced ones.
4. Group lecture + lab pairs (e.g. CSEN 194 + CSEN 194L) in the SAME quarter.
5. If a course is only offered in certain quarters (Fall/Spring), note that in reason.
6. Each course must appear in EXACTLY ONE quarter — no duplicates, no omissions.
7. Use only the term names from the NEXT TERMS list above.
8. graduation_term = the last term in your plan.
9. total_remaining_units = {total_units} (sum of all course units above).
10. advice: 1-3 sentence overview of the plan strategy (max 400 chars).
11. reason per course: ≤60 chars, explain why it belongs in that quarter.

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
    required_codes: set[str] = {
        str(item.get("course") or "").strip().upper()
        for item in missing_details
        if item.get("course")
    }

    def _is_valid_course(course_code: str) -> bool:
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
