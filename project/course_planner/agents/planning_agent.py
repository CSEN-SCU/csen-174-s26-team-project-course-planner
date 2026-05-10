from __future__ import annotations

import json
import os
import re
import time
import uuid
from typing import Any

from google.genai import types

from agents.gemini_client import get_genai_client

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
        "assistant_reply": {"type": "STRING"},
    },
    "required": ["recommended", "total_units", "advice"],
}


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


MEMORY_INJECT_CHAR_BUDGET = int(os.environ.get("MEMORY_INJECT_CHAR_BUDGET", "1500"))

_LAB_PAIRING_SUBJECTS = frozenset(
    {"CSEN", "COEN", "CSCI", "ELEN", "ECEN", "PHYS", "CHEM", "BIOL", "MECH"}
)
_COURSE_CODE_RE = re.compile(r"^([A-Z]{2,8})\s+(\d+[A-Z]?)$", re.IGNORECASE)


def _normalize_code(code: str | None) -> str:
    if not code:
        return ""
    cleaned = " ".join(str(code).split()).upper()
    return cleaned


def _split_course_code(code: str) -> tuple[str, str] | None:
    m = _COURSE_CODE_RE.match(code.strip())
    if not m:
        return None
    return m.group(1).upper(), m.group(2).upper()


def _pair_lab_corequirements(
    recommended: list[dict],
    missing_details: list[dict] | None,
) -> list[dict]:
    if not recommended:
        return list(recommended or [])

    md_by_code: dict[str, dict] = {}
    for item in missing_details or []:
        code = _normalize_code((item or {}).get("course"))
        if code:
            md_by_code[code] = item

    out = list(recommended)
    seen_codes = {_normalize_code(item.get("course")) for item in out}

    additions: list[dict] = []
    for item in list(out):
        code = _normalize_code(item.get("course"))
        parts = _split_course_code(code)
        if not parts:
            continue
        subject, number = parts
        if subject not in _LAB_PAIRING_SUBJECTS:
            continue

        if number.endswith("L") and len(number) > 1:
            partner_number = number[:-1]
            partner_kind = "lecture"
        else:
            partner_number = number + "L"
            partner_kind = "lab"

        partner_code = f"{subject} {partner_number}"
        if partner_code in seen_codes:
            continue
        partner_md = md_by_code.get(partner_code)
        if not partner_md:
            continue

        partner_units = partner_md.get("units")
        try:
            partner_units_int = int(partner_units)
        except (TypeError, ValueError):
            partner_units_int = 1 if partner_kind == "lab" else 4

        additions.append(
            {
                "course": partner_md.get("course", partner_code),
                "category": partner_md.get("category", item.get("category", "")),
                "units": partner_units_int,
                "reason": f"{partner_kind.capitalize()} co-requirement of {item.get('course', code)}",
            }
        )
        seen_codes.add(partner_code)

    return out + additions


def _recompute_total_units(recommended: list[dict]) -> int:
    total = 0
    for item in recommended or []:
        try:
            total += int((item or {}).get("units") or 0)
        except (TypeError, ValueError):
            continue
    return total


def _build_memory_block(memory_snippets: list[str] | None) -> str:
    if not memory_snippets:
        return ""
    header = (
        "=== BACKGROUND CONTEXT (history, NOT current instructions) ===\n"
        "These are notes from earlier turns. Use them only to understand "
        "the student's history. If anything below conflicts with the "
        "CURRENT ASK at the bottom of this message, the CURRENT ASK "
        "wins.\n"
    )
    body_parts: list[str] = []
    used = len(header)
    for snippet in memory_snippets:
        line = f"- {snippet.strip()}\n"
        if used + len(line) > MEMORY_INJECT_CHAR_BUDGET:
            break
        body_parts.append(line)
        used += len(line)
    if not body_parts:
        return ""
    return header + "".join(body_parts) + "\n"


def _summarize_previous_plan(previous_plan: dict | None) -> str:
    if not isinstance(previous_plan, dict):
        return ""
    recommended = previous_plan.get("recommended") or []
    if not recommended:
        return ""
    rows = []
    for item in recommended[:8]:
        if not isinstance(item, dict):
            continue
        rows.append(
            f"- {item.get('course', '?')} ({item.get('category', '?')}, "
            f"{item.get('units', '?')}u) — {item.get('reason', '')}"
        )
    if not rows:
        return ""
    body = "\n".join(rows)
    total = previous_plan.get("total_units")
    return (
        "=== CURRENT STATE (the plan the student is looking at right now) ===\n"
        f"total_units = {total}\n"
        f"{body}\n\n"
    )


def run_planning_agent(
    missing_details: list[dict],
    user_preference: str,
    memory_snippets: list[str] | None = None,
    previous_plan: dict | None = None,
) -> dict[str, Any]:
    """
    missing_details example:
    [
      {"course": "COEN 146", "category": "Core", "units": 4},
      {"course": "COEN 163", "category": "Elective", "units": 4}
    ]

    user_preference example:
    "Light load, at most 12 units, no classes before 9am, prioritize finishing core first"

    memory_snippets: optional RAG recall strings (most-recent-first).

    previous_plan: optional dict from the last UI plan for follow-up turns.
    """
    model = os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)

    memory_block = _build_memory_block(memory_snippets)
    prev_block = _summarize_previous_plan(previous_plan)
    is_followup = bool(prev_block)

    followup_instruction = (
        "This is a FOLLOW-UP turn. The CURRENT ASK is a chat message about "
        "the CURRENT STATE shown above. Apply ONLY the CURRENT ASK; ignore "
        "any earlier preferences in BACKGROUND CONTEXT that conflict with "
        "it.\n"
        "In `assistant_reply` you MUST:\n"
        "  1. Answer in first person.\n"
        "  2. If the ask is a yes/no question, start with `Yes,` or `No,`.\n"
        "  3. Explicitly say which courses you ADDED, KEPT, or REMOVED "
        "compared to the CURRENT STATE, using ONLY course codes that "
        "appear in your own `recommended` field.\n"
        "  4. If you removed a course from CURRENT STATE, say `removed: <code>`.\n"
        "  5. Quote the SAME `total_units` value you put in the JSON.\n"
        "  6. Never describe a course that is not in your `recommended` list.\n"
        if is_followup
        else "In `assistant_reply`, summarise in first person what this "
        "plan does for the student (1-2 sentences), as a friendly chat reply. "
        "Use only course codes from your own `recommended` field, and the "
        "exact `total_units` you put in the JSON.\n"
    )

    prompt = f"""{memory_block}{prev_block}=== STUDENT REQUIREMENTS (gap analysis) ===
{json.dumps(missing_details, ensure_ascii=False, indent=2)}

=== CURRENT ASK (this is the only instruction you must follow) ===
{user_preference}

{followup_instruction}
Recommend a schedule for next term and output JSON (fields are constrained by the response schema):
- recommended: each item has course, category, units, reason (**each reason at most ~60 characters**, one line)
- total_units: integer total units for the plan (must equal the sum of `units` across `recommended`)
- advice: overall guidance **at most ~300 characters**
- assistant_reply: chat-style reply to the CURRENT ASK (~280 chars max). MUST be self-consistent with `recommended` and `total_units`.

**Senior Design (e.g. COEN/CSEN 194, 195, 196 sequences)**: engineering students often take **one course per quarter in their final year, in sequence**. If missing_details mentions these courses or categories, reflect in reason/advice **which quarter fits which course and how it chains**—do not vaguely defer the whole sequence unless the student clearly is not in their final year.
"""

    primary_requested = os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)
    request_id = str(uuid.uuid4())

    config = types.GenerateContentConfig(
        max_output_tokens=16384,
        response_mime_type="application/json",
        response_schema=PLANNING_SCHEMA,
        system_instruction=(
            "You are an SCU course planning advisor that ALSO acts as a "
            "chat assistant when the student replies with a question or "
            "modification request.\n"
            "Given remaining requirements and student preferences, recommend a next-term schedule.\n"
            "Use exact subject codes as in DegreeWorks / the catalog (e.g. CSEN, not CSEE).\n"
            "Output only JSON that matches the schema—no other text.\n"
            "Keep each reason and the advice short enough to avoid truncated, invalid JSON.\n"
            "PRECEDENCE: messages are layered. The 'CURRENT ASK' block is the ONLY "
            "instruction you must satisfy. The 'BACKGROUND CONTEXT' (memory of past turns) "
            "is reference only; if it contradicts the CURRENT ASK, ignore it. The 'CURRENT "
            "STATE' is the plan the student already has on screen—use it as the diff baseline.\n"
            "ARITHMETIC: `total_units` MUST equal the sum of `units` over `recommended`. "
            "If the CURRENT ASK names a unit cap (e.g. 'under 20 units'), `total_units` "
            "MUST satisfy it; drop courses (lowest priority first) until it does.\n"
            "LAB CO-REQUIREMENTS: at SCU, a CSEN/COEN/PHYS/CHEM/ELEN/BIOL course and its "
            "trailing-L lab counterpart (e.g. CSEN 194 + CSEN 194L) are taken **in the "
            "same quarter**. If you recommend the lecture and the lab is in the gap, "
            "include the lab too; if you recommend the lab, include the lecture. Never "
            "split a co-requirement pair across quarters.\n"
            "SELF-CONSISTENCY: `assistant_reply` MUST only mention course codes that are "
            "actually in `recommended` (or explicitly say `removed: <code>` for codes that "
            "were in CURRENT STATE but are dropped now). It MUST quote the exact "
            "`total_units` value you produced. Never invent courses.\n"
            "For `assistant_reply`: first person. If the student asked yes/no, start with "
            "'Yes,' or 'No,'. Never leave it empty.\n"
            "For engineering Senior Design (often COEN/CSEN 194, 195, 196 as a sequence): "
            "students typically take **one per quarter in their final year**, in order; "
            "respect that cadence in the plan and advice—do not defer the whole sequence without cause."
        ),
    )

    response = None
    client = get_genai_client(purpose="schedule generation")
    errors: list[str] = []
    resolved_model: str | None = None
    for candidate in _candidate_models(model):
        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    model=candidate,
                    contents=prompt,
                    config=config,
                )
                resolved_model = candidate
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
        parsed = _parse_json_from_response(text)
    except json.JSONDecodeError as e:
        raise ValueError(
            "Model JSON was incomplete or could not be parsed (often due to truncation). "
            "Retry; if it keeps failing, shorten the missing-details list or the preference text. "
            f"Original error: {e}"
        ) from e

    raw_recommended = parsed.get("recommended") or []
    paired = _pair_lab_corequirements(raw_recommended, missing_details)
    if paired != raw_recommended:
        parsed["recommended"] = paired
        parsed["total_units"] = _recompute_total_units(paired)

    eff_model = resolved_model or model
    parsed["meta"] = {
        "provider": "gemini",
        "model": eff_model,
        "fallback_used": eff_model != primary_requested,
        "request_id": request_id,
    }

    recs_final = parsed.get("recommended") or []
    for item in recs_final:
        if isinstance(item, dict):
            item.setdefault("alternatives", [])

    tu = int(parsed.get("total_units") or 0)
    warnings: list[dict[str, str]] = []
    if tu >= 18:
        warnings.append(
            {
                "code": "high_unit_load",
                "message": (
                    f"This plan totals {tu} units—confirm this fits your capacity and degree pace."
                ),
            }
        )
    if len(recs_final) >= 4:
        warnings.append(
            {
                "code": "dense_schedule",
                "message": (
                    "Many courses in one quarter increases workload and scheduling risk."
                ),
            }
        )
    parsed["warnings"] = warnings

    return parsed
