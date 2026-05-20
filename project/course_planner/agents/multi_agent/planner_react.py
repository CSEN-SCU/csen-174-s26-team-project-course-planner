"""Tool-calling (ReAct) Planner for the multi-agent graph.

The base planner node was a single prompt → JSON call. This upgrades it to
a ReAct loop where Gemini can *decide* to call tools before committing to a
plan:

  - search_schedule(subject)            — what's actually offered next term
  - get_open_req_candidates(req_text)   — which courses satisfy an open Core
  - get_lab_partner(course_code)        — required lab co-requisite (or none)

Uses the native ``google.genai`` function-calling API (no langchain
dependency) so it reuses the existing ``get_genai_client`` and the existing
test-stub pattern. The loop is bounded (``MAX_TOOL_TURNS``) so a misbehaving
model can't spin forever.

``run_planner_react`` returns ``(plan_dict, tool_calls_made)`` — the second
value lets tests assert which tools the model invoked.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from google.genai import types

from agents.gemini_client import get_genai_client
from agents.multi_agent.tools import (
    tool_get_lab_partner,
    tool_get_open_req_candidates,
    tool_search_schedule,
)

log = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-2.5-flash"
MAX_TOOL_TURNS = 5

# ── Function declarations exposed to Gemini ──────────────────────────────────

_FUNCTION_DECLARATIONS = [
    types.FunctionDeclaration(
        name="search_schedule",
        description=(
            "List courses offered in the next-term schedule, optionally filtered "
            "by subject prefix (e.g. 'CSEN'). Use this to confirm a course is "
            "actually offered before recommending it."
        ),
        parameters={
            "type": "OBJECT",
            "properties": {
                "subject": {
                    "type": "STRING",
                    "description": "Subject prefix like CSEN, MATH, ENGL. Omit for all.",
                }
            },
        },
    ),
    types.FunctionDeclaration(
        name="get_open_req_candidates",
        description=(
            "For an open Core/GE requirement string (e.g. 'Core: ENGR: RTC 3'), "
            "return the courses in next-term schedule that satisfy it. Use this "
            "for any requirement that lacks an explicit course code."
        ),
        parameters={
            "type": "OBJECT",
            "properties": {
                "requirement_text": {"type": "STRING"},
            },
            "required": ["requirement_text"],
        },
    ),
    types.FunctionDeclaration(
        name="get_lab_partner",
        description=(
            "Return the required lab co-requisite code for a lecture (e.g. "
            "'CSEN 122' -> 'CSEN 122L'), or null if none. Always check this for "
            "CSEN/COEN/ECEN/ELEN/PHYS/CHEM/BIOL/MECH lectures."
        ),
        parameters={
            "type": "OBJECT",
            "properties": {
                "course_code": {"type": "STRING"},
            },
            "required": ["course_code"],
        },
    ),
]

# Dispatch table: name → callable(args_dict) -> JSON-serializable result.
_TOOL_DISPATCH = {
    "search_schedule": lambda a: tool_search_schedule(a.get("subject")),
    "get_open_req_candidates": lambda a: tool_get_open_req_candidates(
        a.get("requirement_text", "")
    ),
    "get_lab_partner": lambda a: tool_get_lab_partner(a.get("course_code", "")),
}

_SYSTEM = (
    "You are the Planner agent in a multi-agent course planner. Before you "
    "finalize, USE THE TOOLS to (a) confirm each course you pick is in the "
    "next-term schedule, (b) resolve open Core/GE requirements to real "
    "courses, and (c) attach the lab co-requisite for any STEM lecture. "
    "When you are confident, STOP calling tools and output the final plan as "
    "JSON only."
)


def _extract_function_calls(resp: Any) -> list[Any]:
    """Return the list of function-call objects in a response, robust to the
    SDK shape and to test stubs that only set ``.text``."""
    fcs = getattr(resp, "function_calls", None)
    if fcs:
        return list(fcs)
    try:
        parts = resp.candidates[0].content.parts
        return [p.function_call for p in parts if getattr(p, "function_call", None)]
    except Exception:  # noqa: BLE001
        return []


def _parse_plan_json(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if m:
        text = m.group(1).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        log.warning("planner_react: unparseable final JSON: %r", text[:200])
        return {"recommended": []}
    return parsed if isinstance(parsed, dict) else {"recommended": []}


def run_planner_react(
    prompt: str,
    *,
    model: str | None = None,
    client: Any = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Run the planner as a bounded ReAct tool-calling loop.

    Returns ``(plan_dict, tool_calls_made)``.
    """
    model = model or os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)
    if client is None:
        client = get_genai_client(purpose="multi-agent planner (react)")

    tools = [types.Tool(function_declarations=_FUNCTION_DECLARATIONS)]
    config = types.GenerateContentConfig(
        max_output_tokens=8192,
        tools=tools,
        system_instruction=_SYSTEM,
    )

    contents: list[Any] = [types.Content(role="user", parts=[types.Part(text=prompt)])]
    tool_calls_made: list[dict[str, Any]] = []

    for _turn in range(MAX_TOOL_TURNS):
        resp = client.models.generate_content(model=model, contents=contents, config=config)
        fcalls = _extract_function_calls(resp)

        if not fcalls:
            return _parse_plan_json(getattr(resp, "text", "") or ""), tool_calls_made

        # Append the model's tool-call turn so the follow-up has context.
        try:
            contents.append(resp.candidates[0].content)
        except Exception:  # noqa: BLE001
            # Stub responses may not carry candidates; synthesize a placeholder.
            contents.append(
                types.Content(
                    role="model",
                    parts=[types.Part(text="(tool call)")],
                )
            )

        # Execute each requested tool and feed results back.
        response_parts = []
        for fc in fcalls:
            name = getattr(fc, "name", "")
            args = dict(getattr(fc, "args", None) or {})
            tool_calls_made.append({"name": name, "args": args})
            fn = _TOOL_DISPATCH.get(name)
            if fn is None:
                result: Any = {"error": f"unknown tool {name!r}"}
            else:
                try:
                    result = fn(args)
                except Exception as e:  # noqa: BLE001
                    log.warning("planner_react: tool %s failed: %s", name, e)
                    result = {"error": str(e)}
            response_parts.append(
                types.Part.from_function_response(name=name, response={"result": result})
            )
        contents.append(types.Content(role="user", parts=response_parts))

    # Tool budget exhausted — make one final no-tools call to force a plan.
    final_cfg = types.GenerateContentConfig(
        max_output_tokens=8192,
        response_mime_type="application/json",
        system_instruction=_SYSTEM,
    )
    resp = client.models.generate_content(model=model, contents=contents, config=final_cfg)
    return _parse_plan_json(getattr(resp, "text", "") or ""), tool_calls_made
