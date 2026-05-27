from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from agents.four_year_planning_agent import run_four_year_plan_agent
from deps.user_auth import require_matching_user
from middleware.rate_limit import limit

router = APIRouter()


class FourYearPlanRequest(BaseModel):
    missing_details: list[dict[str, Any]] = Field(default_factory=list)
    parsed_rows: list[dict[str, Any]] = Field(default_factory=list)
    user_id: str = ""
    preferences: str = ""
    student_major_id: str = ""


@router.post(
    "",
    include_in_schema=True,
    dependencies=[Depends(limit("four_year_plan"))],
)
def create_four_year_plan(body: FourYearPlanRequest, request: Request) -> dict[str, Any]:
    if body.user_id.strip():
        require_matching_user(request, body.user_id)
    if not body.missing_details:
        raise HTTPException(
            status_code=400,
            detail="Upload your Academic Progress xlsx first so I can see your remaining requirements.",
        )
    try:
        plan = run_four_year_plan_agent(
            body.missing_details,
            preferences=body.preferences or None,
            parsed_rows=body.parsed_rows or None,
            confirmed_major_id=body.student_major_id or None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {"type": "four-year-plan", **plan}
