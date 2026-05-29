from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from agents.memory_agent import write as memory_write
from deps.user_auth import require_matching_user
from utils.major_requirements import (
    detect_major_detailed,
    load_major_index,
    major_display_name,
    sanitize_major_id,
)

router = APIRouter()


class MajorDetectRequest(BaseModel):
    missing_details: list[dict[str, Any]] = Field(default_factory=list)
    parsed_rows: list[dict[str, Any]] = Field(default_factory=list)
    confirmed_major_id: str = ""


class MajorConfirmRequest(BaseModel):
    user_id: str = ""
    major_id: str = ""
    source: str = "user"


@router.get("")
def list_majors() -> dict[str, Any]:
    """All majors with scraped bulletin markdown (from index.json)."""
    index = load_major_index()
    majors = []
    for entry in index.get("majors") or []:
        if not isinstance(entry, dict):
            continue
        majors.append(
            {
                "major_id": entry.get("major_id"),
                "name": entry.get("name"),
                "school": entry.get("school"),
                "markdown_path": entry.get("markdown_path"),
            }
        )
    return {"version": index.get("version"), "majors": majors}


@router.post("/detect")
def detect_major(body: MajorDetectRequest) -> dict[str, Any]:
    """Infer major from Workday export; user-confirmed id overrides inference."""
    confirmed = sanitize_major_id(body.confirmed_major_id.strip() or None)
    if confirmed:
        return {
            "major_id": confirmed,
            "name": major_display_name(confirmed),
            "confidence": "high",
            "needs_confirmation": False,
            "candidates": [],
            "message": f"Using your selected major: {major_display_name(confirmed)} ({confirmed}).",
            "source": "user",
        }

    return {**detect_major_detailed(body.missing_details, body.parsed_rows), "source": "inferred"}


@router.post("/confirm")
def confirm_major(body: MajorConfirmRequest, request: Request) -> dict[str, Any]:
    """Persist the student's confirmed major for future plan requests."""
    uid = body.user_id.strip()
    mid = sanitize_major_id(body.major_id)
    if uid:
        require_matching_user(request, uid)
    if not mid:
        return {"ok": False, "error": "major_id required"}

    name = major_display_name(mid) or mid
    payload = {
        "major_id": mid,
        "name": name,
        "source": body.source or "user",
        "confirmed": True,
    }
    if uid:
        memory_write(uid, "student_major", json.dumps(payload))

    return {"ok": True, **payload}
