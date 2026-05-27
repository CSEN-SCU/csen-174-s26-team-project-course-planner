"""Signed session tokens for API requests after Google OAuth exchange.

The frontend stores the token in sessionStorage and sends
``Authorization: Bearer <token>`` on memory/plan/upload routes so clients
cannot read or write another user's ``user_id`` by guessing small integers.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time


def _signing_key() -> bytes:
    return os.environ.get("SCU_PLANNER_COOKIE_KEY", "dev-cookie-key-change-me").encode(
        "utf-8"
    )


def _max_age_sec() -> int:
    return int(os.environ.get("PLANNER_SESSION_MAX_AGE_SEC", str(7 * 24 * 3600)))


def session_auth_required() -> bool:
    """When true (default), protected routes require a valid Bearer token."""
    return os.environ.get("REQUIRE_PLANNER_SESSION", "1").strip() not in (
        "0",
        "false",
        "False",
    )


def mint_session_token(user_id: str) -> str:
    """Issue a signed session token for the given numeric user id."""
    uid = str(user_id).strip()
    if not uid:
        raise ValueError("user_id is required for session token.")
    ts = str(int(time.time()))
    payload = f"session.{uid}.{ts}"
    sig = hmac.new(_signing_key(), payload.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{uid}.{ts}.{sig}"


def verify_session_token(token: str) -> str:
    """Return user_id if the token is valid and not expired."""
    parts = (token or "").split(".")
    if len(parts) != 3:
        raise ValueError("Invalid session token format.")
    user_id, ts_str, sig = parts
    if not user_id.strip():
        raise ValueError("Invalid session token user id.")
    try:
        ts = int(ts_str)
    except ValueError as exc:
        raise ValueError("Invalid session token timestamp.") from exc
    expected = hmac.new(
        _signing_key(),
        f"session.{user_id}.{ts_str}".encode("ascii"),
        hashlib.sha256,
    ).hexdigest()
    if not secrets.compare_digest(sig, expected):
        raise ValueError("Invalid session token signature.")
    now = int(time.time())
    if now - ts > _max_age_sec() or ts - now > 60:
        raise ValueError("Session token expired.")
    return user_id.strip()
