"""Verify the caller's session matches the requested user_id."""

from __future__ import annotations

from fastapi import HTTPException, Request

from auth.session_token import session_auth_required, verify_session_token


def _bearer_token(request: Request) -> str | None:
    auth = (request.headers.get("authorization") or "").strip()
    if not auth.lower().startswith("bearer "):
        return None
    token = auth[7:].strip()
    return token or None


def require_matching_user(request: Request, user_id: str) -> str:
    """Ensure the path/body user_id matches the signed session token.

    When ``REQUIRE_PLANNER_SESSION=0`` (tests), this is a no-op.
    """
    uid = str(user_id or "").strip()
    if not uid:
        raise HTTPException(status_code=400, detail="user_id is required.")
    if not session_auth_required():
        return uid
    token = _bearer_token(request)
    if not token:
        raise HTTPException(
            status_code=401,
            detail="Missing session. Sign in again with Google.",
        )
    try:
        session_uid = verify_session_token(token)
    except ValueError as exc:
        raise HTTPException(
            status_code=401,
            detail="Session expired or invalid. Sign in again with Google.",
        ) from exc
    if session_uid != uid:
        raise HTTPException(status_code=403, detail="Not allowed to access this user.")
    return uid
