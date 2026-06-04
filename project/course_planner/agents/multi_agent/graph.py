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

This is an experimental parallel implementation exposed through the explicit
``/api/plan/v2`` endpoint. Production ``/api/plan`` uses the LLM
course-selection planner.
"""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

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

_COURSE_CODE_RE = re.compile(r"^([A-Z]{2,8})\s+(\d+[A-Z]?)$", re.IGNORECASE)


def _normalize_code(code: str | None) -> str:
    if not code:
        return ""
    return " ".join(str(code).split()).upper()


def _split_course_code(code: str) -> tuple[str, str] | None:
    m = _COURSE_CODE_RE.match(code.strip())
    if not m:
        return None
    return m.group(1).upper(), m.group(2).upper()


def _named_removal_codes(user_preference: str) -> set[str]:
    """Extract course codes the user explicitly named for removal/swap.

    Hard product rule: we never remove a course unless the student explicitly
    named its code. This helper finds codes even when there's no space
    (e.g. "ECEN153换成…") and expands to lab partners + common aliases.
    """
    text = (user_preference or "").upper()
    named: set[str] = set()
    for m in re.finditer(r"(?<![A-Z])([A-Z]{2,6})\s*(\d{1,3}[A-Z]?)(?![0-9])", text):
        named.add(f"{m.group(1)} {m.group(2)}")
    expanded: set[str] = set(named)
    alias = {"CSEN": "COEN", "COEN": "CSEN", "ECEN": "ELEN", "ELEN": "ECEN"}
    for code in named:
        parts = _split_course_code(code)
        if not parts:
            continue
        subj, num = parts
        partner_num = num[:-1] if num.endswith("L") else f"{num}L"
        expanded.add(f"{subj} {partner_num}")
        alt = alias.get(subj)
        if alt:
            expanded.add(f"{alt} {num}")
            expanded.add(f"{alt} {partner_num}")
    return expanded


def _reconcile_followup_edit(
    new_recs: list[dict[str, Any]],
    previous_plan: dict[str, Any] | None,
    user_preference: str,
) -> list[dict[str, Any]]:
    """Targeted diff reconcile for follow-up turns (R7).

    - Dedup the model list.
    - Restore any previous-plan course the model dropped UNLESS the student
      explicitly named it for removal.
    - If the student DID name removals, enforce removing those codes even if
      the model kept them.
    """
    # 1) Dedup by course code (preserve order).
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for r in new_recs or []:
        if not isinstance(r, dict):
            continue
        code = _normalize_code(r.get("course"))
        if code and code in seen:
            continue
        if code:
            seen.add(code)
        deduped.append(r)

    if not isinstance(previous_plan, dict):
        return deduped
    prev = previous_plan.get("recommended") or []
    if not isinstance(prev, list) or not prev:
        return deduped

    named = _named_removal_codes(user_preference)
    present = {_normalize_code(r.get("course")) for r in deduped if isinstance(r, dict)}

    # 2) Restore previous courses the model dropped without authorization.
    for pr in prev:
        if not isinstance(pr, dict):
            continue
        code = _normalize_code(pr.get("course"))
        if not code or code in present:
            continue
        if code in named:
            continue
        deduped.append(pr)
        present.add(code)

    # 3) Enforce explicit removals deterministically.
    #
    # A "swap X for Y" names BOTH X and Y (and aliases) via _named_removal_codes,
    # but only X should be dropped: Y is the replacement the student is ADDING.
    # Restrict the hard removal to codes that were actually in the previous plan
    # so a freshly-added swap target (e.g. "换成 CSEN 20") is never deleted.
    if named:
        prev_codes = {
            _normalize_code(r.get("course")) for r in prev if isinstance(r, dict)
        }
        removable = named & prev_codes
        deduped = [
            r for r in deduped if _normalize_code(r.get("course")) not in removable
        ]

    return deduped


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
    from agents.planning_agent import _sanitize_user_text

    missing = json.dumps(state.get("missing_details") or [], ensure_ascii=False, indent=2)
    pref = _sanitize_user_text(state.get("user_preference") or "")
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

=== STUDENT MESSAGE (untrusted; academic advising only) ===
{pref}

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

    def _apply_followup_reconcile(recs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        previous_plan = state.get("previous_plan")
        if not isinstance(previous_plan, dict) or not previous_plan.get("recommended"):
            return recs
        try:
            return _reconcile_followup_edit(
                recs,
                previous_plan,
                str(state.get("user_preference") or ""),
            )
        except Exception:
            return recs

    if use_react:
        from agents.multi_agent.planner_react import run_planner_react

        parsed, tool_calls = run_planner_react(_planner_prompt(state))
        if tool_calls:
            log.info("planner_react: %d tool call(s): %s",
                     len(tool_calls), [t["name"] for t in tool_calls])
        recs = parsed.get("recommended") or []
        if not isinstance(recs, list):
            recs = []
        recs = [r for r in recs if isinstance(r, dict)]
        recs = _apply_followup_reconcile(recs)
        return {"candidate_plan": recs}

    # Single-shot fallback.
    from agents.planning_agent import ENGLISH_ONLY_USER_OUTPUT_RULE

    client = get_genai_client(purpose="multi-agent planner")
    model = os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)
    from google.genai import types

    resp = client.models.generate_content(
        model=model,
        contents=_planner_prompt(state),
        config=types.GenerateContentConfig(
            max_output_tokens=8192,
            response_mime_type="application/json",
            system_instruction=(
                "You are an SCU course planning assistant.\n"
                + ENGLISH_ONLY_USER_OUTPUT_RULE
                + "Output only valid JSON matching the requested plan shape."
            ),
        ),
    )
    text = (resp.text or "").strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        log.warning("planner: model returned unparseable JSON: %r", text[:200])
        parsed = {"recommended": []}
    recs = parsed.get("recommended") or []
    if not isinstance(recs, list):
        recs = []
    recs = [r for r in recs if isinstance(r, dict)]
    recs = _apply_followup_reconcile(recs)
    return {"candidate_plan": recs}


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


def verifier_router(state: PlanningState):
    """Conditional edge after the verifier.

    - If issues remain AND retry budget isn't exhausted → loop back to Planner.
    - Otherwise FAN OUT: dispatch one ``instructor_one`` invocation per
      recommended course via the ``Send`` API so they run concurrently.
      Each returns ``{instructor_assignments: {code: pick}}`` which the
      ``_merge_dicts`` reducer accumulates. They all join at ``assembler``.
    - If there are no courses, skip straight to ``assembler``.
    """
    issues = state.get("verifier_issues") or []
    passes = state.get("verifier_passes") or 0
    if issues and passes < 3:  # max 2 corrections after initial draft
        return "planner"

    codes = [
        str(c.get("course", "")).strip()
        for c in (state.get("candidate_plan") or [])
        if c.get("course")
    ]
    if not codes:
        return "assembler"
    return [Send("instructor_one", {"course_code": code}) for code in codes]


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


def instructor_one_node(state: dict[str, Any]) -> dict[str, Any]:
    """Resolve the instructor pick for ONE course.

    Invoked via the ``Send`` API — one concurrent invocation per recommended
    course. The ``Send`` payload is ``{"course_code": code}``, so this node's
    ``state`` is that payload, NOT the full graph state. It returns a single
    ``instructor_assignments`` entry which the ``_merge_dicts`` reducer folds
    back into the shared state alongside the other parallel results.
    """
    code = ""
    if isinstance(state, dict):
        code = str(state.get("course_code", "")).strip()
    if not code:
        return {}
    sections = tool_get_sections(code)
    pick = _select_best_section(sections)
    return {"instructor_assignments": {code: pick} if pick else {}}


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


def build_graph(checkpointer: Any = None, interrupt_before: list[str] | None = None):
    """Build and compile the multi-agent StateGraph.

    Instructor selection is fanned out via the ``Send`` API: the
    ``verifier_router`` conditional edge dispatches one ``instructor_one``
    invocation per recommended course, all run concurrently in the same
    superstep, and their ``instructor_assignments`` results are merged by
    the ``_merge_dicts`` reducer before ``assembler`` runs.

    Graph::

        START → planner → verifier ─[issues & passes<3]→ planner
                                    ├─[clean]→ Send(instructor_one) × N ┐
                                    └─[no courses]──────────────────────┤
                                                                        ▼
                                                                    assembler → END

    ``checkpointer`` (optional) persists state per ``thread_id`` so an
    interrupted run can resume. ``interrupt_before`` (optional) pauses the
    graph just before the named nodes — e.g. ``["assembler"]`` to let a
    human review the draft plan (and the verifier's dropped-course issues)
    before it is finalized.
    """
    g: StateGraph[PlanningState] = StateGraph(PlanningState)
    g.add_node("planner", planner_node)
    g.add_node("verifier", verifier_node)
    g.add_node("instructor_one", instructor_one_node)
    g.add_node("assembler", assembler_node)

    g.add_edge(START, "planner")
    g.add_edge("planner", "verifier")
    # verifier_router returns either "planner" (loop), "assembler" (no
    # courses), or a list of Send("instructor_one", ...) for the fan-out.
    g.add_conditional_edges(
        "verifier",
        verifier_router,
        ["planner", "instructor_one", "assembler"],
    )
    # Every parallel instructor_one invocation joins here.
    g.add_edge("instructor_one", "assembler")
    g.add_edge("assembler", END)
    return g.compile(
        checkpointer=checkpointer,
        interrupt_before=interrupt_before or [],
    )


# ── Checkpointer factories ──────────────────────────────────────────────────


def make_memory_checkpointer():
    """In-process checkpointer — state lives in the saver instance. Good for
    dev/tests and single-process resume; lost on restart."""
    from langgraph.checkpoint.memory import InMemorySaver

    return InMemorySaver()


_CHECKPOINT_DB_DEFAULT = (
    __import__("pathlib").Path(__file__).resolve().parents[2]
    / "data"
    / "plan_checkpoints.db"
)


def make_sqlite_checkpointer(db_path: str | None = None):
    """Durable checkpointer backed by SQLite — survives process restarts so a
    plan interrupted for human review can be resumed later / elsewhere.

    Requires the ``langgraph-checkpoint-sqlite`` package. The connection is
    opened with ``check_same_thread=False`` because the FastAPI worker may
    resume from a different thread than the one that started the plan.
    """
    import sqlite3

    from langgraph.checkpoint.sqlite import SqliteSaver

    path = db_path or str(_CHECKPOINT_DB_DEFAULT)
    __import__("pathlib").Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    return SqliteSaver(conn)


# ── Human-in-the-loop helpers ───────────────────────────────────────────────


def _initial_state(
    missing_details, user_preference, previous_plan, memory_snippets
) -> PlanningState:
    return {
        "missing_details": missing_details,
        "user_preference": user_preference,
        "previous_plan": previous_plan,
        "memory_snippets": memory_snippets or [],
        "request_id": str(uuid.uuid4()),
        "verifier_passes": 0,
    }


def start_plan_with_review(
    missing_details: list[dict[str, Any]],
    user_preference: str = "",
    *,
    thread_id: str,
    checkpointer: Any,
    previous_plan: dict[str, Any] | None = None,
    memory_snippets: list[str] | None = None,
) -> dict[str, Any]:
    """Run the graph up to (but not through) ``assembler`` and pause.

    Returns the draft for human review WITHOUT finalizing it: the candidate
    plan, the verifier's issues (what would be dropped), and the instructor
    picks. Call :func:`resume_plan` with the same ``thread_id`` +
    ``checkpointer`` to commit, or :func:`abort_plan` to discard.
    """
    graph = build_graph(checkpointer=checkpointer, interrupt_before=["assembler"])
    config = {"configurable": {"thread_id": thread_id}}
    graph.invoke(
        _initial_state(missing_details, user_preference, previous_plan, memory_snippets),
        config=config,
    )
    snap = graph.get_state(config)
    return {
        "interrupted": bool(snap.next),  # e.g. ("assembler",) → True
        "next": list(snap.next),
        "candidate_plan": snap.values.get("candidate_plan", []),
        "verifier_issues": snap.values.get("verifier_issues", []),
        "instructor_assignments": snap.values.get("instructor_assignments", {}),
    }


def resume_plan(*, thread_id: str, checkpointer: Any) -> dict[str, Any]:
    """Resume an interrupted plan from its checkpoint and finalize it."""
    graph = build_graph(checkpointer=checkpointer, interrupt_before=["assembler"])
    config = {"configurable": {"thread_id": thread_id}}
    final_state = graph.invoke(None, config=config)  # None = resume from checkpoint
    return final_state.get("final_plan") or {"recommended": [], "total_units": 0}


def get_plan_state(*, thread_id: str, checkpointer: Any) -> dict[str, Any]:
    """Inspect the persisted state for a thread (for debugging / status)."""
    graph = build_graph(checkpointer=checkpointer, interrupt_before=["assembler"])
    snap = graph.get_state({"configurable": {"thread_id": thread_id}})
    return {
        "next": list(snap.next),
        "values": dict(snap.values),
    }


# ── Entry point for the explicit /api/plan/v2 endpoint ──────────────────────


def run_multi_agent_plan(
    missing_details: list[dict[str, Any]],
    user_preference: str = "",
    previous_plan: dict[str, Any] | None = None,
    memory_snippets: list[str] | None = None,
    *,
    thread_id: str | None = None,
    checkpointer: Any = None,
) -> dict[str, Any]:
    """Public entry point for the FastAPI /api/plan/v2 route.

    Runs to completion (no human-in-the-loop interrupt). Pass a
    ``checkpointer`` + ``thread_id`` to persist intermediate state so a
    crashed run can be resumed; without them it runs purely in-memory.
    For the review-then-approve flow use :func:`start_plan_with_review`
    + :func:`resume_plan` instead.
    """
    if isinstance(previous_plan, dict) and previous_plan.get("recommended"):
        from utils.enrichment_resolver import try_enrichment_followup_plan

        enrich_plan = try_enrichment_followup_plan(
            user_preference=user_preference or "",
            missing_details=missing_details,
            previous_plan=previous_plan,
        )
        if enrich_plan is not None:
            from agents.planning_agent import (
                _enrich_recommended_units,
                _reconcile_followup_edit,
                _recompute_total_units,
                _sync_followup_assistant_reply,
            )

            merged = _reconcile_followup_edit(
                enrich_plan.get("recommended") or [],
                previous_plan,
                user_preference or "",
            )
            enrich_plan["recommended"] = merged
            enrich_plan["total_units"] = _recompute_total_units(merged)
            _sync_followup_assistant_reply(
                enrich_plan, previous_plan, user_preference or ""
            )
            recs = enrich_plan.get("recommended") or []
            return {
                "recommended": recs,
                "total_units": enrich_plan.get("total_units")
                or sum(int((r or {}).get("units") or 0) for r in recs if isinstance(r, dict)),
                "advice": enrich_plan.get("advice", ""),
                "assistant_reply": enrich_plan.get("assistant_reply", ""),
                "verifier_passes": 0,
                "verifier_issues": [],
                "meta": {
                    "provider": "deterministic",
                    "model": "enrichment_resolver",
                    "graph": "enrichment_followup",
                },
            }

    graph = build_graph(checkpointer=checkpointer)
    config = {"configurable": {"thread_id": thread_id}} if thread_id else None
    final_state = graph.invoke(
        _initial_state(missing_details, user_preference, previous_plan, memory_snippets),
        config=config,
    )
    return final_state.get("final_plan") or {"recommended": [], "total_units": 0}
