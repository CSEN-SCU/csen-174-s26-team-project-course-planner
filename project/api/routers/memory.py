from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from agents.memory_agent import ALLOWED_KINDS, delete, list_for_user, write

router = APIRouter()


class MemoryWriteBody(BaseModel):
    content: str = ""
    type: str = Field(..., description="Memory kind: preference | plan_outcome | note")


@router.get("/{user_id}")
def get_memory(user_id: str) -> dict[str, Any]:
    try:
        items = list_for_user(user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"memories": items}


@router.delete("/{user_id}/{item_id}")
def delete_memory(user_id: str, item_id: int) -> dict[str, Any]:
    try:
        found = delete(user_id, item_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if not found:
        raise HTTPException(status_code=404, detail="Memory item not found.")
    return {"success": True}


@router.post("/{user_id}")
def append_memory(user_id: str, body: MemoryWriteBody) -> dict[str, Any]:
    kind = body.type.strip()
    if kind not in ALLOWED_KINDS:
        raise HTTPException(
            status_code=400,
            detail=f"type must be one of: {', '.join(ALLOWED_KINDS)}",
        )
    if not body.content or not body.content.strip():
        raise HTTPException(status_code=400, detail="content must be non-empty.")
    try:
        new_id = write(user_id, kind, body.content.strip())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"success": True, "id": new_id}
