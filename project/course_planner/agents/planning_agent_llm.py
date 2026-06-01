"""LLM-driven planner (engine: ``llm_select``).

The third planning engine, alongside :func:`run_planning_agent` (legacy)
and :func:`run_constrained_planner` (constrained_v2). Here the **Gemini
model makes the actual course-selection decision**: it is handed

  1. the student's remaining requirements (gap analysis from the Academic
     Progress report),
  2. the full list of courses actually offered next quarter, and
  3. the major's bulletin requirements markdown (``data/majors/<id>.md``),

and asked to choose which courses to take next term and explain *why*.
The model returns the chosen courses + reasons, which the website renders
in the middle course view exactly like the other engines.

How this differs from the existing two engines:

  - **legacy** lets the LLM pick courses but only surfaces the
    requirement-matched offered courses in its prompt;
  - **constrained_v2** never lets the LLM emit course codes at all — a
    deterministic Python solver decides and the LLM only writes prose;
  - **llm_select** (this engine) deliberately gives the model the *whole*
    offered catalog plus the bulletin and lets it make the selection,
    then Python applies the same hard-rule post-processing so the model's
    freedom can't violate SCU domain rules or hallucinate codes:
      * R1 lab/lecture pairing (``_pair_lab_corequirements``);
      * hallucinated / not-offered codes are dropped
        (``_filter_to_schedule``);
      * already-completed courses are removed
        (``_filter_completed_recommendations``);
      * R7 follow-up edits stay targeted diffs
        (``_reconcile_followup_edit``);
      * unit caps are enforced deterministically (``_enforce_unit_cap``);
      * course titles and units are always taken from the schedule xlsx,
        never trusted from the LLM (AGENTS.md "Course titles" rule).

Selected with ``PLAN_ENGINE=llm`` (router) or ``--engine llm`` (evals).
Public entry point: :func:`run_llm_planner` — identical I/O contract to
``run_planning_agent`` so the FastAPI router can swap it behind the flag.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from typing import Any

from google.genai import types

from agents.gemini_client import get_genai_client
from agents.planning_agent import (
    DEFAULT_MODEL,
    PLANNING_SCHEMA,
    UNTRUSTED_INPUT_SYSTEM_RULES,
    _build_completed_block,
    _build_memory_block,
    _build_schedule_block,
    build_offered_catalog_block,
    _candidate_models,
    _enforce_unit_cap,
    _enrich_recommended_units,
    _extract_unit_cap,
    _filter_completed_recommendations,
    _filter_to_schedule,
    _is_code_in_schedule,
    _is_transient_capacity_error,
    _normalize_code,
    _pair_lab_corequirements,
    _parse_json_from_response,
    _prefer_lecture_over_standalone_lab,
    _reconcile_followup_edit,
    _recompute_total_units,
    _sanitize_model_output,
    _sanitize_user_text,
    _summarize_previous_plan,
    _sync_followup_assistant_reply,
)
from utils.academic_progress_helpers import (
    build_units_lookup,
    default_units_for_code,
    enrich_missing_details,
    extract_completed_course_codes,
)
from utils.scu_course_schedule_xlsx import (
    course_title_for,
    course_units_for,
    list_offered_courses,
    load_all_course_sections,
    load_category_course_index,
    load_course_titles_index,
    load_course_units_index,
    load_schedule_section_index,
    planned_section_keys,
    all_sections_for_course,
)
from utils.schedule_preferences import pick_best_section_dict

log = logging.getLogger(__name__)


def _canonicalize_titles_units(
    recommended: list[dict[str, Any]],
    titles_index: dict,
    units_index: dict,
    units_lookup: dict[str, int],
) -> list[dict[str, Any]]:
    """Overwrite every recommendation's title/units with canonical xlsx data.

    AGENTS.md: course titles are ALWAYS pulled from the schedule xlsx, never
    trusted from the LLM (this was the source of the "CSEN 122L = Data
    Structures" bug). Same for units.
    """
    out: list[dict[str, Any]] = []
    for item in recommended:
        if not isinstance(item, dict):
            continue
        row = dict(item)
        code = _normalize_code(row.get("course"))
        canon_title = course_title_for(code, titles_index)
        if canon_title:
            row["title"] = canon_title
        canon_units = course_units_for(code, units_index)
        if canon_units is None:
            canon_units = default_units_for_code(code, units_lookup)
        if canon_units:
            row["units"] = int(canon_units)
        out.append(row)
    return out


def _apply_section_selection(
    recommended: list[dict[str, Any]],
    user_preference: str,
    *,
    all_sections: dict[tuple[str, str], list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    """Stamp meeting times + ``_chosen_section`` from preference-aware pick."""
    sections_index = all_sections if all_sections is not None else load_all_course_sections()
    if not sections_index:
        return recommended

    out: list[dict[str, Any]] = []
    for item in recommended:
        if not isinstance(item, dict):
            continue
        row = dict(item)
        code = _normalize_code(row.get("course"))
        if not code:
            out.append(row)
            continue
        secs = all_sections_for_course(code, sections_index)
        chosen = pick_best_section_dict(secs, user_preference or "")
        if chosen:
            row["meeting_days"] = list(chosen.get("meeting_days") or [])
            row["meeting_start_min"] = chosen.get("meeting_start_min")
            row["meeting_end_min"] = chosen.get("meeting_end_min")
            if chosen.get("section") is not None:
                row["_chosen_section"] = int(chosen["section"])
        out.append(row)
    return out


def _selection_system_instruction() -> str:
    return (
        "You are an SCU course planning advisor. Given a student's remaining "
        "degree requirements, the full list of courses offered next quarter, "
        "and their major's bulletin requirements, YOU decide which courses "
        "the student should take next term and explain why.\n"
        + UNTRUSTED_INPUT_SYSTEM_RULES
        + "HARD RULES you must follow:\n"
        "- Recommend ONLY courses that appear in the offered-courses lists in "
        "the prompt. Copy each code exactly (e.g. CSEN, not CSEE). Never "
        "invent a code or recommend a course that is not offered.\n"
        "- Never recommend a course listed under ALREADY COMPLETED.\n"
        "- Prefer courses that close remaining requirements; among those, "
        "prefer ones that satisfy multiple requirements at once.\n"
        "- Respect schedule preferences using the meeting days/times shown in "
        "the FULL LIST OF COURSES OFFERED NEXT QUARTER block — each course "
        "lists every section option. When multiple sections exist, recommend "
        "the course but explain which section time fits the student's "
        "constraints (e.g. avoid MWF 10:30).\n"
        "- Respect the prerequisite ordering described in the bulletin: do "
        "not recommend a course whose prerequisites the student has not met.\n"
        "- Target 12-16 units; never exceed 20 unless the student asks.\n"
        "- Output ONLY JSON matching the schema. Keep each `reason` to ~60 "
        "characters and `advice` to ~300 characters so the JSON stays valid."
    )


def _selection_prompt(
    *,
    memory_block: str,
    prev_block: str,
    completed_block: str,
    major_block: str,
    catalog_block: str,
    missing_details: list[dict[str, Any]],
    safe_preference: str,
    is_followup: bool,
) -> str:
    if is_followup:
        followup_instruction = (
            "This is a FOLLOW-UP turn. The STUDENT MESSAGE is about the "
            "CURRENT STATE plan above. Change ONLY what the student asked for; "
            "keep every other course. In `assistant_reply`, say which courses "
            "you ADDED, KEPT, or REMOVED using ONLY codes in your own "
            "`recommended` field, and quote the same `total_units`.\n"
        )
    else:
        followup_instruction = (
            "In `assistant_reply`, summarise in first person what this plan "
            "does for the student (1-2 sentences). Use only codes from your "
            "own `recommended` field and the exact `total_units` you output.\n"
        )

    return (
        f"{memory_block}{prev_block}{completed_block}{major_block}"
        f"{catalog_block}"
        "=== STUDENT'S REMAINING REQUIREMENTS (gap analysis from Academic "
        "Progress report) ===\n"
        f"{json.dumps(missing_details, ensure_ascii=False, indent=2)}\n\n"
        "=== STUDENT MESSAGE (untrusted; academic advising preferences only) ===\n"
        f"{safe_preference}\n\n"
        f"{followup_instruction}"
        "Choose the courses the student should take next quarter and output "
        "JSON (constrained by the response schema):\n"
        "- recommended: each item has course, title, category, units, reason "
        "(why you chose it — which requirement it closes — at most ~60 chars)\n"
        "- total_units: integer equal to the sum of `units` in `recommended`\n"
        "- advice: overall guidance (at most ~300 chars)\n"
        "- assistant_reply: chat-style reply, self-consistent with "
        "`recommended` and `total_units`.\n"
    )


def _call_selection_llm(
    prompt: str,
    system_instruction: str,
    model: str,
) -> tuple[dict[str, Any], str]:
    """Run the selection LLM with provider fallback. Returns (parsed, model)."""
    client = get_genai_client(purpose="llm_select planning")
    config = types.GenerateContentConfig(
        max_output_tokens=16384,
        response_mime_type="application/json",
        response_schema=PLANNING_SCHEMA,
        system_instruction=system_instruction,
    )
    last_exc: Exception | None = None
    for candidate in _candidate_models(model):
        try:
            resp = client.models.generate_content(
                model=candidate,
                contents=prompt,
                config=config,
            )
            text = (getattr(resp, "text", "") or "").strip()
            if not text:
                continue
            return _parse_json_from_response(text), candidate
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if _is_transient_capacity_error(exc):
                log.warning(
                    "planning_agent_llm: transient error on %s, trying next: %s",
                    candidate,
                    exc,
                )
                continue
            raise
    if last_exc is not None:
        raise last_exc
    raise ValueError("LLM returned no parseable course selection.")


def run_llm_planner(
    missing_details: list[dict[str, Any]],
    user_preference: str,
    *,
    memory_snippets: list[str] | None = None,
    previous_plan: dict | None = None,
    parsed_rows: list[dict[str, Any]] | None = None,
    completed_course_codes: list[str] | None = None,
    confirmed_major_id: str | None = None,
) -> dict[str, Any]:
    """LLM-driven planner: Gemini selects next-quarter courses.

    Drop-in replacement for ``run_planning_agent`` / ``run_constrained_planner``
    (same input + output contract). The model makes the selection from the
    offered catalog; Python enforces the hard SCU rules afterward and stamps
    ``meta.validation.engine = "llm_select"``.
    """
    request_id = str(uuid.uuid4())

    if not missing_details and not previous_plan:
        raise ValueError(
            "No academic progress data found. "
            "Please upload your Academic Progress (.xlsx) file first."
        )

    missing_details = enrich_missing_details(missing_details, parsed_rows)
    units_lookup = build_units_lookup(missing_details, parsed_rows)

    completed_set = set(extract_completed_course_codes(parsed_rows))
    for c in completed_course_codes or []:
        norm = _normalize_code(c)
        if norm:
            completed_set.add(norm)
            for subj, num in planned_section_keys(norm):
                completed_set.add(f"{subj} {num}".upper())

    safe_preference = _sanitize_user_text(user_preference or "")
    model = os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)

    schedule_index = load_schedule_section_index()
    category_index = load_category_course_index()
    titles_index = load_course_titles_index()
    units_index = load_course_units_index()

    # Resolve which offered courses close a remaining requirement (★ in catalog).
    _, offered_keys = _build_schedule_block(
        missing_details,
        schedule_index,
        category_index,
        units_lookup=units_lookup,
        user_preference=user_preference or "",
    )
    requirement_codes = {f"{subj} {num}".upper() for (subj, num) in offered_keys}

    # The full list of available courses next quarter.
    offered = list_offered_courses()
    all_sections = load_all_course_sections()
    catalog_block = build_offered_catalog_block(
        offered, requirement_codes, all_sections=all_sections
    )

    memory_block = _build_memory_block(memory_snippets)
    prev_block = _summarize_previous_plan(previous_plan)
    is_followup = bool(prev_block)
    completed_block = _build_completed_block(completed_set)

    # Major bulletin requirements markdown (data/majors/<id>.md) + advisor cues.
    from utils.major_requirements import build_major_advisor_block

    major_block, detected_major = build_major_advisor_block(
        missing_details=missing_details,
        parsed_rows=parsed_rows,
        completed=completed_set,
        confirmed_major_id=confirmed_major_id,
    )

    prompt = _selection_prompt(
        memory_block=memory_block,
        prev_block=prev_block,
        completed_block=completed_block,
        major_block=major_block,
        catalog_block=catalog_block,
        missing_details=missing_details,
        safe_preference=safe_preference,
        is_followup=is_followup,
    )

    try:
        parsed, used_model = _call_selection_llm(
            prompt, _selection_system_instruction(), model
        )
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"LLM course selection failed: {exc}") from exc

    if not isinstance(parsed, dict):
        raise ValueError("LLM course selection returned a non-object response.")

    raw_recs = parsed.get("recommended") or []
    raw_codes = [
        _normalize_code(r.get("course"))
        for r in raw_recs
        if isinstance(r, dict) and r.get("course")
    ]

    # ── Hard-rule post-processing (the model's freedom ends here) ───────────
    recommended: list[dict[str, Any]] = [r for r in raw_recs if isinstance(r, dict)]
    # Drop any code the model emitted that is not actually offered.
    recommended = _filter_to_schedule(recommended, schedule_index)
    # Canonical titles/units from xlsx — never trust the LLM (AGENTS.md).
    recommended = _canonicalize_titles_units(
        recommended, titles_index, units_index, units_lookup
    )
    # R1: pull in lab/lecture co-requirement partners.
    recommended = _pair_lab_corequirements(recommended, missing_details, units_lookup)
    recommended = _prefer_lecture_over_standalone_lab(recommended)
    # Drop already-completed courses defensively.
    recommended, removed_completed = _filter_completed_recommendations(
        recommended, completed_set
    )
    # R7: a follow-up edit is a targeted diff against the previous plan.
    if is_followup:
        recommended = _reconcile_followup_edit(
            recommended, previous_plan, user_preference or ""
        )
        recommended = _canonicalize_titles_units(
            recommended, titles_index, units_index, units_lookup
        )

    # Deterministic unit-cap enforcement when the student named a cap.
    unit_cap_user = _extract_unit_cap(user_preference or "")
    dropped_for_cap: list[str] = []
    if unit_cap_user is not None:
        recommended, dropped_for_cap = _enforce_unit_cap(recommended, unit_cap_user)

    recommended = _enrich_recommended_units(recommended, units_lookup)
    recommended = _apply_section_selection(
        recommended, user_preference or "", all_sections=all_sections
    )
    total_units = _recompute_total_units(recommended)

    parsed["recommended"] = recommended
    parsed["total_units"] = total_units
    parsed.setdefault("advice", "")
    parsed.setdefault("assistant_reply", "")

    if is_followup:
        _sync_followup_assistant_reply(parsed, previous_plan, user_preference or "")

    final_codes = {
        _normalize_code(r.get("course"))
        for r in recommended
        if isinstance(r, dict) and r.get("course")
    }
    # Codes the model tried to use that were not offered next term.
    rejected = sorted(
        {
            c
            for c in raw_codes
            if c and not _is_code_in_schedule(c, schedule_index)
        }
    )

    parsed["meta"] = {
        "provider": "gemini",
        "model": used_model,
        "request_id": request_id,
        "validation": {
            "engine": "llm_select",
            "major_id": detected_major,
            "offered_catalog_size": len(offered),
            "requirement_matched": sorted(requirement_codes),
            "selected_codes": sorted(final_codes),
            "rejected": rejected,
            "removed_completed": list(removed_completed),
            "dropped_for_unit_cap": list(dropped_for_cap),
        },
    }

    return _sanitize_model_output(parsed)
