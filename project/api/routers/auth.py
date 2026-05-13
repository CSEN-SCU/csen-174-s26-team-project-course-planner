from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import time
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from auth import oauth_state
from auth.users_db import (
    UserAlreadyExistsError,
    create_user,
    get_or_create_user_for_google,
    get_user_by_username,
    verify_login,
)

logger = logging.getLogger(__name__)
router = APIRouter()


class LoginBody(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class RegisterBody(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class GoogleExchangeBody(BaseModel):
    token: str = Field(..., min_length=1)


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


# ---------------------------------------------------------------------------
# Google OAuth (authorization code + stateless PKCE)
# ---------------------------------------------------------------------------

_HANDOFF_MAX_AGE_SEC = 120


def _signing_key() -> bytes:
    """Shared HMAC key for OAuth state + frontend handoff tokens.

    Reuses ``SCU_PLANNER_COOKIE_KEY`` so production deployments only have
    to manage one secret. Dev default is fine because tokens are short-
    lived and only meaningful to this server.
    """
    return os.environ.get("SCU_PLANNER_COOKIE_KEY", "dev-cookie-key-change-me").encode("utf-8")


def _frontend_base_url() -> str:
    return os.environ.get("FRONTEND_BASE_URL", "http://localhost:5173").rstrip("/")


def _mint_handoff_token(user_id: str) -> str:
    """Short-lived signed token the backend hands to the frontend after a successful
    Google sign-in. Frontend POSTs it to ``/exchange`` to read the user_id; this
    prevents a tampered ``?user_id=`` query param from spoofing a session.
    """
    ts = str(int(time.time()))
    payload = f"{user_id}.{ts}"
    sig = hmac.new(_signing_key(), payload.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{user_id}.{ts}.{sig}"


def _verify_handoff_token(token: str) -> str:
    parts = (token or "").split(".")
    if len(parts) != 3:
        raise ValueError("Invalid handoff token format.")
    user_id, ts_str, sig = parts
    try:
        ts = int(ts_str)
    except ValueError as exc:
        raise ValueError("Invalid handoff token timestamp.") from exc
    expected = hmac.new(
        _signing_key(), f"{user_id}.{ts_str}".encode("ascii"), hashlib.sha256
    ).hexdigest()
    if not secrets.compare_digest(sig, expected):
        raise ValueError("Invalid handoff token signature.")
    now = int(time.time())
    if now - ts > _HANDOFF_MAX_AGE_SEC or ts - now > 60:
        raise ValueError("Handoff token expired.")
    return user_id


def _google_module():
    """Lazy import so the API still boots when google-auth wheels are absent."""
    try:
        from auth import google_oauth  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover
        raise HTTPException(
            status_code=503,
            detail="Google sign-in is not available — install google-auth-oauthlib.",
        ) from exc
    return google_oauth


def _frontend_redirect(query: dict[str, str]) -> RedirectResponse:
    return RedirectResponse(url=f"{_frontend_base_url()}/?{urlencode(query)}", status_code=302)


@router.get("/google/start")
def google_start() -> RedirectResponse:
    """Build a Google authorize URL and 302 the browser there.

    The state/nonce/PKCE values are HMAC-derived from a fresh random and
    travel through Google in the ``state`` query param, so the callback
    needs no server-side memory of this attempt.
    """
    google = _google_module()
    if not google.google_oauth_configured():
        raise HTTPException(
            status_code=503,
            detail="Google sign-in is not configured (GOOGLE_CLIENT_ID/SECRET).",
        )
    try:
        state, nonce, verifier = oauth_state.mint_oauth_challenge(_signing_key())
        url = google.build_authorization_url(state, nonce, code_verifier=verifier)
    except Exception:
        logger.exception("Failed to build Google authorize URL")
        raise HTTPException(status_code=500, detail="Could not start Google sign-in.")
    return RedirectResponse(url=url, status_code=302)


@router.get("/google/callback")
def google_callback(request: Request) -> RedirectResponse:
    """Handle Google's redirect: verify state, exchange code, upsert user, redirect
    to the frontend with a short-lived signed handoff token.
    """
    google = _google_module()
    params = request.query_params

    err = params.get("error")
    if err:
        logger.warning("Google OAuth redirect error: %s %s", err, params.get("error_description"))
        return _frontend_redirect({"google_oauth_error": err or "unknown"})

    code = params.get("code")
    state_qp = params.get("state")
    if not code or not state_qp:
        return _frontend_redirect({"google_oauth_error": "missing_params"})

    try:
        nonce, verifier = oauth_state.verify_state_and_derive_secrets(state_qp, _signing_key())
        raw_claims = google.exchange_code_for_id_token(
            state_qp,
            state_qp,
            code,
            expected_nonce=nonce,
            code_verifier=verifier,
        )
        claims = google.validate_sign_in_claims(raw_claims)
        user = get_or_create_user_for_google(
            str(claims["email"]),
            str(claims["sub"]),
        )
        token = _mint_handoff_token(str(user["id"]))
        return _frontend_redirect({"google_oauth": token})
    except (google.OAuthStateError, google.OAuthClaimsError, ValueError) as exc:
        logger.warning("Google OAuth callback rejected: %s", exc)
        return _frontend_redirect({"google_oauth_error": "invalid"})
    except Exception:
        logger.exception("Google OAuth callback failed")
        return _frontend_redirect({"google_oauth_error": "server_error"})


@router.post("/google/exchange")
def google_exchange(body: GoogleExchangeBody) -> dict[str, Any]:
    """Swap a handoff token (from ``/google/callback``) for a usable ``user_id``."""
    try:
        user_id = _verify_handoff_token(body.token)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "user_id": user_id}
