from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from auth.users_db import (
    UserAlreadyExistsError,
    create_user,
    get_user_by_username,
    verify_login,
)

router = APIRouter()


class LoginBody(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class RegisterBody(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


def _placeholder_email(username: str) -> str:
    """Synthetic email for API-only registration (users_db requires an email)."""
    safe = "".join(c for c in username if c.isalnum() or c in "._-") or "user"
    return f"{safe}@api.course-planner.local"


@router.post("/login")
def login(body: LoginBody) -> dict[str, Any]:
    ok = verify_login(body.username, body.password)
    if not ok:
        return {"success": False, "user_id": ""}
    user = get_user_by_username(body.username)
    if user is None:
        return {"success": False, "user_id": ""}
    return {"success": True, "user_id": str(user["id"])}


@router.post("/register")
def register(body: RegisterBody) -> dict[str, Any]:
    email = _placeholder_email(body.username)
    try:
        create_user(body.username, email, body.password)
    except UserAlreadyExistsError:
        return {"success": False}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"success": True}
