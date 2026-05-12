from __future__ import annotations

import json
import os
import re
import time
import uuid
from typing import Any

from google.genai import types

from agents.gemini_client import get_genai_client
from utils.scu_course_schedule_xlsx import load_schedule_section_index, planned_section_keys

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
                    "title": {"type": "STRING"},
                    "category": {"type": "STRING"},
                    "units": {"type": "INTEGER"},
                    "reason": {"type": "STRING"},
                },
                "required": ["course", "title", "category", "units", "reason"],
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


def _extract_codes_from_requirement(text: str) -> list[str]:
    """Extract every course code embedded in a requirement description.

    Handles SCU Workday patterns like:
      "CSEN/COEN 122 & 122L"    → CSEN 122, COEN 122, CSEN 122L, COEN 122L
      "CSEN/COEN 194/L"         → CSEN 194, COEN 194, CSEN 194L, COEN 194L
      "ECEN/ELEN 153 & 153L"    → ECEN 153, ELEN 153, ECEN 153L, ELEN 153L
      "Core: ENGR: RTC 3"       → []  (no usable course code)
    """
    t = text.upper()
    # "194/L" → "194 & 194L"
    t = re.sub(r"(\d+[A-Z]?)/L\b", r"\1 & \1L", t)

    # Find all slash-paired subject groups: "CSEN/COEN" → ["CSEN", "COEN"]
    slash_subj_re = re.compile(r"\b([A-Z]{2,6}(?:/[A-Z]{2,6})+)\b")
    subj_groups: list[list[str]] = []
    subj_group_positions: list[tuple[int, int, list[str]]] = []
    for m in slash_subj_re.finditer(t):
        variants = m.group(0).split("/")
        subj_group_positions.append((m.start(), m.end(), variants))

    # Find all standalone subjects (not part of a slash group)
    solo_subj_re = re.compile(r"\b([A-Z]{2,6})\b")

    # Find all number tokens (course numbers) that follow a subject group
    num_re = re.compile(r"\b(\d{1,3}[A-Z]?)\b")

    codes: list[str] = []
    seen: set[str] = set()

    # Walk through slash-groups and collect the numbers that follow each group
    for start, end, variants in subj_group_positions:
        # Look for numbers in the text after this group (up to the next subject or 60 chars)
        tail = t[end:end + 80]
        nums = num_re.findall(tail)
        # Stop at the first non-number/non-separator token (rough heuristic: take up to 4 nums)
        for num in nums[:4]:
            for subj in variants:
                c = f"{subj} {num}"
                if c not in seen:
                    codes.append(c)
                    seen.add(c)

    # If nothing found via slash-groups, fall back to simple SUBJ NUM pairs
    if not codes:
        simple_re = re.compile(r"\b([A-Z]{2,6})\s+(\d{1,3}[A-Z]?)\b")
        for subj, num in simple_re.findall(t):
            c = f"{subj} {num}"
            if c not in seen:
                codes.append(c)
                seen.add(c)

    return codes


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


def _resolve_item_codes(item: dict) -> list[str]:
    """Return the list of course codes to try for one missing_details item.

    Workday transcripts often have course_code=None with the code embedded
    in the requirement text, e.g. "CSEN/COEN 122 & 122L".  Fall back to
    extracting from the category/requirement field when the course field is empty.
    """
    explicit = (item.get("course") or "").strip()
    if explicit:
        return [explicit]
    for key in ("category", "requirement"):
        text = (item.get(key) or "").strip()
        if text:
            extracted = _extract_codes_from_requirement(text)
            if extracted:
                return extracted
    return []


def _build_schedule_block(
    missing_details: list[dict], schedule_index: dict
) -> tuple[str, set[tuple[str, str]]]:
    """
    Return a prompt block listing which required courses are offered next term,
    and the set of (subject, number) keys that are confirmed in the schedule.
    """
    if not schedule_index:
        return "", set()

    offered: list[dict] = []
    not_offered: list[str] = []
    offered_keys: set[tuple[str, str]] = set()

    for item in missing_details:
        codes = _resolve_item_codes(item)
        if not codes:
            # requirement has no parseable course code (e.g. open-ended Core categories)
            label = (item.get("category") or item.get("requirement") or "unknown")[:60]
            not_offered.append(f"[open requirement: {label}]")
            continue
        found: set[tuple[str, str]] = set()
        for code in codes:
            found |= {k for k in planned_section_keys(code) if k in schedule_index}
        if found:
            # Attach the resolved primary code so the LLM sees an explicit code
            primary = codes[0]
            enriched = {**item, "course": primary}
            offered.append(enriched)
            offered_keys |= found
        else:
            not_offered.extend(codes)

    lines: list[str] = []

    if offered:
        lines.append("=== COURSES CONFIRMED IN NEXT-TERM SCHEDULE ===")
        lines.append(
            "You MUST only recommend courses from the list below. "
            "Copy each course code CHARACTER-FOR-CHARACTER — do not alter, "
            "abbreviate, or substitute any code. "
            "Do NOT invent or guess codes that are not in this list."
        )
        for item in offered:
            code = item.get("course", "?")
            cat = (item.get("category") or item.get("requirement") or "").strip()
            units = item.get("units")
            unit_str = f"{units}u" if units not in (None, "", "?") else "see catalog"
            lines.append(f"  {code} ({cat}, {unit_str})")

    if not_offered:
        lines.append(
            "\n=== NOT OFFERED NEXT TERM — DO NOT RECOMMEND ===\n"
            "The following required courses are NOT available next term. "
            "Do NOT include them in your plan under any circumstances. "
            "Do NOT substitute a similar-sounding or numbered course in their place:\n  "
            + ", ".join(not_offered)
        )

    if not lines:
        return "", set()

    return "\n".join(lines) + "\n\n", offered_keys


def _is_code_in_required(code: str, required_codes: set[str]) -> bool:
    """True if code (or its lab-pair variant) is a real student requirement."""
    norm = code.strip().upper()
    return (
        norm in required_codes
        or (norm.endswith("L") and norm[:-1] in required_codes)
        or (norm + "L") in required_codes
    )


def _is_code_in_schedule(code: str, schedule_index: dict) -> bool:
    """True if the course code exists in the published next-term schedule."""
    return any(k in schedule_index for k in planned_section_keys(code))


def _partition_recommended(
    recommended: list[dict],
    schedule_index: dict,
    required_codes: set[str] | None,
) -> tuple[list[dict], list[dict]]:
    """Split recommendations into (valid, rejected).

    A course is valid when:
      1. It is a real student requirement (if required_codes whitelist available).
      2. It appears in the live next-term schedule index.

    Rejected items carry a ``_rejection_reason`` field for the feedback prompt.
    """
    valid: list[dict] = []
    rejected: list[dict] = []
    for item in recommended:
        code = (item.get("course") or "").strip()
        if required_codes is not None and not _is_code_in_required(code, required_codes):
            rejected.append({**item, "_rejection_reason": "not_a_real_requirement"})
        elif schedule_index and not _is_code_in_schedule(code, schedule_index):
            rejected.append({**item, "_rejection_reason": "not_in_next_term_schedule"})
        else:
            valid.append(item)
    return valid, rejected


def _build_gap_fill_prompt(
    rejected: list[dict],
    valid_so_far: list[dict],
    offered_block: str,
    user_preference: str,
) -> str:
    """Build a targeted prompt that tells the LLM exactly which courses were
    hallucinated and asks it to replace each one with a real alternative."""
    rejected_lines = "\n".join(
        f"  - {item.get('course', '?')} "
        f"(category: {item.get('category', '?')}, "
        f"units: {item.get('units', '?')}) "
        f"→ reason rejected: {item.get('_rejection_reason', 'unknown')}"
        for item in rejected
    )
    already_valid = ", ".join(
        item.get("course", "?") for item in valid_so_far
    ) or "none"
    return f"""=== CORRECTION REQUIRED ===
Your previous plan included courses that do not exist in the next-term schedule
or are not real student requirements. They have been removed:

{rejected_lines}

Courses already confirmed valid (do NOT repeat these): {already_valid}

{offered_block}
=== CURRENT ASK ===
{user_preference}

Replace EACH rejected course above with a real alternative drawn only from the
CONFIRMED NEXT-TERM SCHEDULE list. Output JSON with only the replacement courses
in `recommended` — one replacement per rejected slot where possible.
Keep the same category/unit budget as the course you are replacing.
Do NOT re-invent the rejected codes; do NOT repeat already-valid courses.
"""


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
    # Cannot plan without a requirement list — the schedule block would be empty
    # and the LLM would either hallucinate freely or return 0 courses.
    if not missing_details and not previous_plan:
        raise ValueError(
            "No academic progress data found. "
            "Please upload your Academic Progress (.xlsx) file first."
        )

    model = os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)

    schedule_index = load_schedule_section_index()
    schedule_block, offered_keys = _build_schedule_block(missing_details, schedule_index)

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

    prompt = f"""{memory_block}{prev_block}{schedule_block}=== STUDENT REQUIREMENTS (gap analysis) ===
{json.dumps(missing_details, ensure_ascii=False, indent=2)}

=== CURRENT ASK (this is the only instruction you must follow) ===
{user_preference}

{followup_instruction}
Recommend a schedule for next term and output JSON (fields are constrained by the response schema):
- recommended: each item has course, title (full catalog course name, e.g. "Software Engineering"), category, units, reason (**each reason at most ~60 characters**, one line)
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
            "REAL COURSES ONLY: Every course code you output MUST exist in the official SCU "
            "schedule for next term. Do NOT invent department prefixes (e.g. CREL, PHIL, RELS) "
            "or course numbers that are not listed in the 'COURSES CONFIRMED IN NEXT-TERM "
            "SCHEDULE' block. If no religion/ethics course appears in the confirmed list, do "
            "NOT recommend any religion/ethics course — skip that requirement this term.\n"
            "For `assistant_reply`: first person. If the student asked yes/no, start with "
            "'Yes,' or 'No,'. Never leave it empty.\n"
            "For engineering Senior Design (often COEN/CSEN 194, 195, 196 as a sequence): "
            "students typically take **one per quarter in their final year**, in order; "
            "respect that cadence in the plan and advice—do not defer the whole sequence without cause.\n"
            "DOUBLE-TAGGED COURSES: When filling Core or GE requirements, **always prefer "
            "courses that are double-tagged** (count toward more than one requirement "
            "simultaneously, e.g. a course satisfying both an Ethics Core and a Social Justice "
            "requirement). These give more value per unit. Only override this preference if the "
            "student explicitly requests a specific course or category.\n"
            "COURSE TITLE: The `title` field must be the official full course name from the "
            "SCU catalog (e.g. course='CSEN 174', title='Software Engineering'). Never leave it blank."
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

    # ── Build requirement whitelist ──────────────────────────────────────────
    # Use _resolve_item_codes so we catch codes embedded in requirement text.
    # Expand each code through planned_section_keys to cover CSEN↔COEN aliases
    # and lab variants so the whitelist never rejects a valid alias.
    req_codes: set[str] | None = None
    if missing_details:
        resolved: set[str] = set()
        for item in missing_details:
            for c in _resolve_item_codes(item):
                resolved.add(c.upper())
                for subj, num in planned_section_keys(c):
                    resolved.add(f"{subj} {num}")
                    # Add lab variant (only if not already a lab code)
                    if not num.endswith("L"):
                        resolved.add(f"{subj} {num}L")
                    else:
                        resolved.add(f"{subj} {num[:-1]}")  # base without L
        req_codes = resolved if resolved else None  # None = skip whitelist (open Core)

    # ── Validate → feedback loop (max 2 correction rounds) ──────────────────
    # Instead of silently dropping hallucinated courses, we tell the LLM exactly
    # which codes failed and why, then ask it to produce real replacements.
    valid_courses, rejected = _partition_recommended(
        raw_recommended, schedule_index, req_codes
    )
    for _round in range(2):
        if not rejected:
            break
        gap_prompt = _build_gap_fill_prompt(
            rejected, valid_courses, schedule_block, user_preference
        )
        try:
            gap_resp = client.models.generate_content(
                model=resolved_model or model,
                contents=gap_prompt,
                config=types.GenerateContentConfig(
                    max_output_tokens=4096,
                    response_mime_type="application/json",
                    response_schema=PLANNING_SCHEMA,
                ),
            )
            gap_text = (gap_resp.text or "").strip()
            if gap_text:
                gap_parsed = _parse_json_from_response(gap_text)
                replacements = gap_parsed.get("recommended") or []
                new_valid, still_rejected = _partition_recommended(
                    replacements, schedule_index, req_codes
                )
                valid_courses.extend(new_valid)
                rejected = still_rejected  # retry only what still fails
        except Exception:  # noqa: BLE001
            break  # correction failed — keep what we have

    raw_recommended = valid_courses
    # ────────────────────────────────────────────────────────────────────────

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
