from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from agents.memory_agent import list_for_user
from agents.planning_agent import run_planning_agent
from agents.professor_agent import run_professor_agent

router = APIRouter()


class PlanRequest(BaseModel):
    missing_details: list[dict[str, Any]] = Field(default_factory=list)
    user_preference: str = ""
    user_id: str = ""


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

    try:
        plan = run_planning_agent(
            body.missing_details,
            body.user_preference,
            memory_snippets=memory_snippets,
            previous_plan=None,
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

    return {
        "recommended": enriched,
        "total_units": total_units,
        "advice": advice,
    }
