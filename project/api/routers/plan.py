from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, HTTPException
from google.genai import types
from pydantic import BaseModel, Field

from agents.gemini_client import get_genai_client
from agents.memory_agent import list_for_user
from agents.planning_agent import run_planning_agent
from agents.professor_agent import run_professor_agent

router = APIRouter()

_CONVO_START_RE = re.compile(
    r"^\s*(do you|does|is|are|have you|will you|what|where|how|why|when|who|"
    r"tell me|explain|what'?s|what is|what are|am i|did you|"
    r"i have a question|i was wondering)\b",
    re.IGNORECASE,
)
_PLANNING_RE = re.compile(
    r"\b(plan|schedule|recommend|suggest|pick|select|next quarter|next term|"
    r"what courses|which courses|add to my schedule|enroll|register|build me a|"
    r"make me a|give me a schedule|give me courses)\b",
    re.IGNORECASE,
)
# Action verbs that signal a schedule edit request (e.g. "Can you add another course")
_SCHEDULE_EDIT_RE = re.compile(
    r"\b(add|remove|drop|swap|replace|include|exclude)\b.{0,40}\b(course|class|core|elective|credit|unit)\b",
    re.IGNORECASE,
)


def _is_conversational(message: str) -> bool:
    """Return True if the message is a question/chat rather than a planning request."""
    msg = message.strip()
    if _PLANNING_RE.search(msg):
        return False
    if _SCHEDULE_EDIT_RE.search(msg):
        return False
    return bool(_CONVO_START_RE.match(msg))


def _answer_conversational(
    message: str,
    missing_details: list[dict],
    memory_snippets: list[str] | None,
) -> str:
    context_lines: list[str] = []
    if missing_details:
        context_lines.append(
            f"The student HAS uploaded their transcript. "
            f"There are {len(missing_details)} remaining requirements on record."
        )
    else:
        context_lines.append(
            "The student has NOT yet uploaded their transcript (Academic Progress xlsx)."
        )
    if memory_snippets:
        context_lines.append("Recent notes: " + "; ".join(memory_snippets[:2]))

    context = "\n".join(context_lines)
    prompt = (
        f"You are an SCU course planning advisor.\n\n"
        f"Context:\n{context}\n\n"
        f"Student message: {message}\n\n"
        "Reply in 1-3 sentences, first person, friendly and direct. "
        "Do NOT generate a course schedule or list courses. "
        "Just answer the student's question conversationally."
    )

    client = get_genai_client(purpose="conversational Q&A")
    config = types.GenerateContentConfig(max_output_tokens=256)
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=config,
        )
        return (response.text or "").strip()
    except Exception:  # noqa: BLE001
        if missing_details:
            return "Yes, I have your transcript loaded with the requirements on file. What would you like to do next?"
        return "I don't have your transcript yet. Please upload your Academic Progress xlsx file to get started."


class PlanRequest(BaseModel):
    missing_details: list[dict[str, Any]] = Field(default_factory=list)
    user_preference: str = ""
    user_id: str = ""
    previous_plan: dict[str, Any] | None = None


@router.post("", include_in_schema=True)
def create_plan(body: PlanRequest) -> dict[str, Any]:
    memory_snippets: list[str] | None = None
    if body.user_id.strip():
        try:
            items = list_for_user(body.user_id.strip())
            memory_snippets = [
                str(it.get("content") or "")
                for it in items[:12]
                if str(it.get("content") or "").strip()
            ] or None
        except ValueError:
            memory_snippets = None

    # Route conversational questions away from the planning agent
    if _is_conversational(body.user_preference):
        reply = _answer_conversational(
            body.user_preference,
            body.missing_details,
            memory_snippets,
        )
        return {"type": "answer", "reply": reply}

    # If no transcript yet and this is a planning request, ask to upload first
    if not body.missing_details:
        return {
            "type": "answer",
            "reply": "Please upload your Academic Progress xlsx file first so I can see your remaining requirements.",
        }

    try:
        plan = run_planning_agent(
            body.missing_details,
            body.user_preference,
            memory_snippets=memory_snippets,
            previous_plan=body.previous_plan,
        )
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    recs = plan.get("recommended") or []
    if not isinstance(recs, list):
        recs = []

    try:
        enriched = run_professor_agent(recs)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    total = plan.get("total_units", 0)
    try:
        total_units = int(total)
    except (TypeError, ValueError):
        total_units = 0

    advice = plan.get("advice")
    if advice is None:
        advice = ""
    elif not isinstance(advice, str):
        advice = str(advice)

    assistant_reply = plan.get("assistant_reply")
    if assistant_reply is None:
        assistant_reply = ""
    elif not isinstance(assistant_reply, str):
        assistant_reply = str(assistant_reply)

    return {
        "type": "plan",
        "recommended": enriched,
        "total_units": total_units,
        "advice": advice,
        "assistant_reply": assistant_reply,
    }
