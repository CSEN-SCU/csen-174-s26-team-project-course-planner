from __future__ import annotations

import json
import os
import re

from google import genai
from google.genai import types

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client()
    return _client

RESULT_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "completed": {"type": "ARRAY", "items": {"type": "STRING"}},
        "missing": {"type": "ARRAY", "items": {"type": "STRING"}},
        "missing_details": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "course": {"type": "STRING"},
                    "category": {"type": "STRING"},
                    "units": {"type": "INTEGER"},
                },
                "required": ["course", "category", "units"],
            },
        },
    },
    "required": ["completed", "missing", "missing_details"],
}

# New accounts cannot use gemini-2.0-flash; default to a current Gemini API Flash model.
DEFAULT_MODEL = "gemini-2.5-flash"


def _parse_json_from_response(text: str) -> dict:
    text = text.strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if m:
        text = m.group(1).strip()
    return json.loads(text)


def run_requirement_agent(pdf_bytes: bytes, completed_courses: list[str]) -> dict:
    completed_str = json.dumps(completed_courses, ensure_ascii=False)
    model = os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)

    prompt = f"""
You are a university course-planning advisor.

Completed courses (student): {completed_str}

Analyze this major-requirements PDF and determine:
1. Which required courses the student has already completed (cross-check the PDF; list only requirements that appear in the PDF and that the student has taken)
2. Which required courses are still missing

Respond with the agreed JSON structure (fields are constrained by the response schema).
"""

    response = _get_client().models.generate_content(
        model=model,
        contents=[
            types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
            prompt,
        ],
        config=types.GenerateContentConfig(
            max_output_tokens=8192,
            response_mime_type="application/json",
            response_schema=RESULT_SCHEMA,
        ),
    )

    text = (response.text or "").strip()
    if not text:
        raise ValueError("Model returned no text content")
    return _parse_json_from_response(text)
