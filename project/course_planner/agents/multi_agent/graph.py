"""LangGraph multi-agent orchestration: Planner ↔ Verifier ↔ Instructor Selector.

Architecture
============

::

    START ─► Planner ─► Verifier ─►[issues?]
                ▲                       │
                │                       ├── yes ──► Planner (with feedback) ── (max 2 loops)
                │                       │
                │                       └── no
                │                              │
                └── feedback edge              ▼
                                       InstructorSelector (per course)
                                              │
                                              ▼
                                         Assembler ─► END

This module deliberately keeps the LLM-driven nodes thin: each is a single
prompt call to ``planning_agent`` helpers (where reusable) or to Gemini via
the existing client. The graph is the *coordination* layer.

This is a parallel implementation — the existing ``run_planning_agent`` keeps
working unchanged. Plug this into a new endpoint (e.g. ``/api/plan/v2``) or
behind a feature flag when ready.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph

from agents.gemini_client import get_genai_client
from agents.multi_agent.tools import (
    tool_check_in_schedule,
    tool_compare_instructors,
    tool_detect_conflicts,
    tool_get_instructor_rating,
    tool_get_lab_partner,
    tool_get_open_req_candidates,
    tool_get_sections,
    tool_score_double_tag_coverage,
)

log = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-2.5-flash"


# ── Shared state ─────────────────────────────────────────────────────────────


def _merge_dicts(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    """Reducer for the instructor_assignments dict so parallel InstructorSelector
    nodes can each contribute a single course code without clobbering."""
    return {**left, **right}


class PlanningState(TypedDict, total=False):
    # Inputs
    missing_details: list[dict[str, Any]]
    user_preference: str
    previous_plan: dict[str, Any] | None
    memory_snippets: list[str]
    request_id: str

    # Workflow state
    candidate_plan: list[dict[str, Any]]
    verifier_issues: list[dict[str, Any]]
    verifier_passes: int  # number of times the verifier has run

    # Parallel fan-out output
    instructor_assignments: Annotated[dict[str, dict[str, Any]], _merge_dicts]

    # Final
    final_plan: dict[str, Any]


# ── Node 1: Planner ──────────────────────────────────────────────────────────


def _planner_prompt(state: PlanningState) -> str:
    missing = json.dumps(state.get("missing_details") or [], ensure_ascii=False, indent=2)
    pref = state.get("user_preference") or ""
    issues = state.get("verifier_issues") or []
    issue_block = ""
    if issues:
        issue_block = (
            "\n\n=== VERIFIER FEEDBACK (your previous draft had problems) ===\n"
            + json.dumps(issues, ensure_ascii=False, indent=2)
            + "\nFix each issue. Do NOT repeat the same course codes that were rejected."
        )
    return f"""You are the Planner agent. Produce a JSON list of recommended courses for
next term based on the student's remaining requirements.

REMAINING REQUIREMENTS:
{missing}

STUDENT PREFERENCE: {pref!r}

{issue_block}

Output JSON exactly like:
{{
  "recommended": [
    {{"course": "CSEN 122", "category": "Major", "units": 4, "reason": "core architecture"}},
    ...
  ]
}}

Rules:
- Only emit course codes you believe exist in the next-term schedule.
- Each lecture course in CSEN/COEN/ECEN/ELEN/PHYS/CHEM/BIOL/MECH must be
  paired with its ``L`` lab when that lab is also a remaining requirement.
- Target 12–16 units, never exceed 20.
"""


def planner_node(state: PlanningState) -> dict[str, Any]:
    """LLM-driven planner.

    By default runs as a ReAct tool-calling loop (the model can call
    search_schedule / get_open_req_candidates / get_lab_partner before
    committing). Set ``PLANNER_REACT=0`` to fall back to the single-shot
    JSON call (cheaper, no tool use) — useful for cost-sensitive runs.

    Produces ``candidate_plan``.
    """
    use_react = os.environ.get("PLANNER_REACT", "1") != "0"

    if use_react:
        from agents.multi_agent.planner_react import run_planner_react

        parsed, tool_calls = run_planner_react(_planner_prompt(state))
        if tool_calls:
            log.info("planner_react: %d tool call(s): %s",
                     len(tool_calls), [t["name"] for t in tool_calls])
        return {"candidate_plan": parsed.get("recommended") or []}

    # Single-shot fallback.
    client = get_genai_client(purpose="multi-agent planner")
    model = os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)
    from google.genai import types

    resp = client.models.generate_content(
        model=model,
        contents=_planner_prompt(state),
        config=types.GenerateContentConfig(
            max_output_tokens=8192,
            response_mime_type="application/json",
        ),
    )
    text = (resp.text or "").strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        log.warning("planner: model returned unparseable JSON: %r", text[:200])
        parsed = {"recommended": []}
    return {"candidate_plan": parsed.get("recommended") or []}


# ── Node 2: Verifier ─────────────────────────────────────────────────────────


def verifier_node(state: PlanningState) -> dict[str, Any]:
    """Deterministic verifier — runs the existing tool functions. No LLM
    needed here; the rules are encoded in code already."""
    plan = state.get("candidate_plan") or []
    codes = [str(c.get("course", "")).strip() for c in plan if c.get("course")]
    issues: list[dict[str, Any]] = []

    # 1. Hallucination: every code in next-term schedule.
    for code in codes:
        if not tool_check_in_schedule(code):
            issues.append({"type": "hallucinated", "course": code})

    # 2. Time conflicts.
    for a, b, code_a, code_b in tool_detect_conflicts(codes):
        issues.append({"type": "time_conflict", "a": code_a, "b": code_b})

    # 3. Missing lab partners.
    for code in codes:
        partner = tool_get_lab_partner(code)
        if partner and partner not in codes:
            # Only flag if the partner is also in missing_details
            md_text = " ".join(
                str(i.get("requirement", "")) for i in (state.get("missing_details") or [])
            )
            if partner in md_text or partner.replace("L", "") in md_text:
                issues.append({"type": "missing_lab_partner", "lecture": code, "lab": partner})

    # 4. Coverage of open Core/GE requirements (R2: prefer double-tagged).
    open_reqs = [
        str(i.get("requirement", ""))
        for i in (state.get("missing_details") or [])
        if "Core:" in str(i.get("requirement", ""))
    ]
    coverage = tool_score_double_tag_coverage(codes, open_reqs)
    if coverage["uncovered"]:
        issues.append({"type": "uncovered_core_requirement", "uncovered": coverage["uncovered"]})

    passes = (state.get("verifier_passes") or 0) + 1
    return {"verifier_issues": issues, "verifier_passes": passes}


def verifier_router(state: PlanningState) -> str:
    """Edge: if issues remain AND we haven't exhausted retry budget, loop back
    to Planner. Otherwise advance to instructor selection."""
    issues = state.get("verifier_issues") or []
    passes = state.get("verifier_passes") or 0
    if issues and passes < 3:  # max 2 corrections after initial draft
        return "planner"
    return "fan_out_instructor"


# ── Node 3: Instructor Selector (one node per recommended course) ───────────


def _section_rating(section: dict[str, Any]) -> tuple[float, float]:
    """Sort key for a section: (best_instructor_rating, -difficulty).

    Higher rating wins; lower difficulty breaks ties. Sections whose
    instructor has no rating data sort last (rating treated as -1).
    """
    best_rating = -1.0
    best_difficulty = 5.0  # worst, so unknown tie-breaks unfavourably
    for name in section.get("instructors") or []:
        rec = tool_get_instructor_rating(name)
        r = rec.get("rating")
        d = rec.get("difficulty")
        if isinstance(r, (int, float)) and r > best_rating:
            best_rating = float(r)
            best_difficulty = float(d) if isinstance(d, (int, float)) else 5.0
    return (best_rating, -best_difficulty)


def _select_best_section(sections: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Pick the section taught by the highest-rated instructor (R5).

    Ranking: instructor rating desc, then difficulty asc. When NO section
    has rating data, the order is stable (first section wins) so behaviour
    is deterministic. Always surfaces a comparison table of the alternatives
    so the UI can show *why* this section was chosen.
    """
    if not sections:
        return None

    ranked = sorted(sections, key=_section_rating, reverse=True)
    best = ranked[0]
    best_instructors = best.get("instructors") or []
    chosen_instructor = best_instructors[0] if best_instructors else None

    # Comparison = the chosen instructor + every other section's lead
    # instructor, with ratings, so the UI can render a side-by-side table.
    seen: set[str] = set()
    comparison: list[dict[str, Any]] = []
    for sec in ranked:
        for name in (sec.get("instructors") or [])[:1]:
            if name and name not in seen:
                seen.add(name)
                comparison.append(tool_get_instructor_rating(name))

    chosen_rating = (
        tool_get_instructor_rating(chosen_instructor) if chosen_instructor else None
    )

    return {
        "section": best.get("section"),
        "meeting_days": best.get("meeting_days"),
        "meeting_start_min": best.get("meeting_start_min"),
        "meeting_end_min": best.get("meeting_end_min"),
        "instructor": chosen_instructor,
        "instructor_rating": chosen_rating,
        # alternatives = comparison minus the chosen instructor (first entry)
        "alternatives": [c for c in comparison if c.get("instructor") != chosen_instructor],
    }


def make_instructor_node(course_code: str):
    """Factory: returns a node that resolves the instructor pick for one
    specific course. Used to fan out — one node per recommended code."""
    def _node(state: PlanningState) -> dict[str, Any]:
        sections = tool_get_sections(course_code)
        pick = _select_best_section(sections)
        return {"instructor_assignments": {course_code: pick} if pick else {}}
    return _node


# ── Node 4: Assembler ───────────────────────────────────────────────────────


def assembler_node(state: PlanningState) -> dict[str, Any]:
    """Merge the candidate plan with instructor picks into the final shape
    that the FastAPI route returns."""
    enriched: list[dict[str, Any]] = []
    for entry in state.get("candidate_plan") or []:
        code = str(entry.get("course", "")).strip()
        assign = (state.get("instructor_assignments") or {}).get(code)
        enriched.append({**entry, "section": assign})

    final = {
        "recommended": enriched,
        "total_units": sum(int(e.get("units") or 0) for e in enriched),
        "verifier_passes": state.get("verifier_passes", 0),
        "verifier_issues": state.get("verifier_issues") or [],
        "meta": {
            "provider": "gemini",
            "model": os.environ.get("GEMINI_MODEL", DEFAULT_MODEL),
            "request_id": state.get("request_id") or str(uuid.uuid4()),
            "graph": "multi_agent_v1",
        },
    }
    return {"final_plan": final}


# ── Graph construction ─────────────────────────────────────────────────────-


def build_graph():
    """Build and compile the multi-agent StateGraph.

    Note: instructor selection is *not* fanned out across N parallel nodes
    in this v1 build — that would require dynamic graph construction
    (one node per recommended code) which LangGraph doesn't natively
    support without ``Send`` API. We use a single sequential node that
    loops through codes; the graph shape is in place for the parallel
    upgrade once R5 (instructor ratings) lands.
    """
    g: StateGraph[PlanningState] = StateGraph(PlanningState)
    g.add_node("planner", planner_node)
    g.add_node("verifier", verifier_node)
    g.add_node("fan_out_instructor", _all_instructors_node)
    g.add_node("assembler", assembler_node)

    g.add_edge(START, "planner")
    g.add_edge("planner", "verifier")
    g.add_conditional_edges(
        "verifier",
        verifier_router,
        {"planner": "planner", "fan_out_instructor": "fan_out_instructor"},
    )
    g.add_edge("fan_out_instructor", "assembler")
    g.add_edge("assembler", END)
    return g.compile()


def _all_instructors_node(state: PlanningState) -> dict[str, Any]:
    """Sequential aggregator that resolves instructor picks for every
    course in the candidate plan. Replaces a true Send-based fan-out for
    now (see ``build_graph`` docstring)."""
    assignments: dict[str, dict[str, Any]] = {}
    for entry in state.get("candidate_plan") or []:
        code = str(entry.get("course", "")).strip()
        if not code:
            continue
        sections = tool_get_sections(code)
        pick = _select_best_section(sections)
        if pick:
            assignments[code] = pick
    return {"instructor_assignments": assignments}


# ── Entry point analogous to ``run_planning_agent`` ─────────────────────────


def run_multi_agent_plan(
    missing_details: list[dict[str, Any]],
    user_preference: str = "",
    previous_plan: dict[str, Any] | None = None,
    memory_snippets: list[str] | None = None,
) -> dict[str, Any]:
    """Public entry point. Same signature as the existing
    ``run_planning_agent`` so the FastAPI route can swap behind a flag."""
    initial_state: PlanningState = {
        "missing_details": missing_details,
        "user_preference": user_preference,
        "previous_plan": previous_plan,
        "memory_snippets": memory_snippets or [],
        "request_id": str(uuid.uuid4()),
        "verifier_passes": 0,
    }
    graph = build_graph()
    final_state = graph.invoke(initial_state)
    return final_state.get("final_plan") or {"recommended": [], "total_units": 0}
