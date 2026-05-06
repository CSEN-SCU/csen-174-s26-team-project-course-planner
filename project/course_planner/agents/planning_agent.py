from __future__ import annotations

import json
import os
import re
import time
from typing import Any

from google import genai
from google.genai import types

_client: genai.Client | None = None

DEFAULT_MODEL = "gemini-2.5-flash"
FALLBACK_MODELS = ("gemini-2.5-flash-lite", "gemini-1.5-flash")

PLANNING_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "recommended": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "course": {"type": "STRING"},
                    "category": {"type": "STRING"},
                    "units": {"type": "INTEGER"},
                    "reason": {"type": "STRING"},
                },
                "required": ["course", "category", "units", "reason"],
            },
        },
        "total_units": {"type": "INTEGER"},
        "advice": {"type": "STRING"},
    },
    "required": ["recommended", "total_units", "advice"],
}


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not key:
            raise ValueError(
                "GEMINI_API_KEY (or GOOGLE_API_KEY) is not set; cannot generate a recommended schedule."
            )
        _client = genai.Client(api_key=key)
    return _client


def _parse_json_from_response(text: str) -> dict[str, Any]:
    text = text.strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if m:
        text = m.group(1).strip()
    return json.loads(text)


def _is_transient_capacity_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "503" in msg or "unavailable" in msg or "high demand" in msg


def _candidate_models(primary_model: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for model in (primary_model, *FALLBACK_MODELS):
        if model and model not in seen:
            seen.add(model)
            out.append(model)
    return out


def run_planning_agent(missing_details: list[dict], user_preference: str) -> dict[str, Any]:
    """
    missing_details example:
    [
      {"course": "COEN 146", "category": "Core", "units": 4},
      {"course": "COEN 163", "category": "Elective", "units": 4}
    ]

    user_preference example:
    "Light load, at most 12 units, no classes before 9am, prioritize finishing core first"
    """
    model = os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)

    prompt = f"""
Courses the student still needs to take:
{json.dumps(missing_details, ensure_ascii=False, indent=2)}

Student preferences:
{user_preference}

Recommend a schedule for next term and output JSON (fields are constrained by the response schema):
- recommended: each item has course, category, units, reason (**each reason at most ~60 characters**, one line)
- total_units: integer total units for the plan
- advice: overall guidance **at most ~300 characters**

**Senior Design (e.g. COEN/CSEN 194, 195, 196 sequences)**: engineering students often take **one course per quarter in their final year, in sequence**. If missing_details mentions these courses or categories, reflect in reason/advice **which quarter fits which course and how it chains**—do not vaguely defer the whole sequence unless the student clearly is not in their final year.
"""

    config = types.GenerateContentConfig(
        # Long outputs can truncate and yield invalid JSON (e.g. unterminated strings)
        max_output_tokens=16384,
        response_mime_type="application/json",
        response_schema=PLANNING_SCHEMA,
        system_instruction=(
            "You are an SCU course planning advisor.\n"
            "Given remaining requirements and student preferences, recommend a next-term schedule.\n"
            "Use exact subject codes as in DegreeWorks / the catalog (e.g. CSEN, not CSEE).\n"
            "Output only JSON that matches the schema—no other text.\n"
            "Keep each reason and the advice short enough to avoid truncated, invalid JSON.\n"
            "For engineering Senior Design (often COEN/CSEN 194, 195, 196 as a sequence): "
            "students typically take **one per quarter in their final year**, in order; "
            "respect that cadence in the plan and advice—do not defer the whole sequence without cause."
        ),
    )

    response = None
    client = _get_client()
    errors: list[str] = []
    for candidate in _candidate_models(model):
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
                if not _is_transient_capacity_error(e) or attempt == 2:
                    continue
                time.sleep(1.5 * (2**attempt))
        if response is not None:
            break

    if response is None:
        raise ValueError(
            "Schedule generation failed after retries and fallback models. "
            "Please retry in 1-2 minutes. Details: "
            + " | ".join(errors[-3:])
        )

    text = (response.text or "").strip()
    if not text:
        raise ValueError("Model returned no text content")
    try:
        return _parse_json_from_response(text)
    except json.JSONDecodeError as e:
        raise ValueError(
            "Model JSON was incomplete or could not be parsed (often due to truncation). "
            "Retry; if it keeps failing, shorten the missing-details list or the preference text. "
            f"Original error: {e}"
        ) from e
