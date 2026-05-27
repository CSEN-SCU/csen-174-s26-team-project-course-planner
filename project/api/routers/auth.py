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
from auth.session_token import mint_session_token
from agents.memory_agent import delete_all_for_user, purge_user_storage
from auth.users_db import (
    delete_user_by_id,
    get_or_create_user_for_google,
    get_user_by_id,
)

logger = logging.getLogger(__name__)
router = APIRouter()


class GoogleExchangeBody(BaseModel):
    token: str = Field(..., min_length=1)


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
    return {
        "success": True,
        "user_id": user_id,
        "session_token": mint_session_token(user_id),
    }


@router.delete("/user/{user_id}/data")
def delete_user_data(user_id: str, request: Request) -> dict[str, Any]:
    """Remove all stored data for this user (memory file + SQLite account).

    Purges memory first so a stale browser session still clears data even when
    the SQLite user row was lost (e.g. ephemeral disk on Render after redeploy).
    """
    from deps.user_auth import require_matching_user

    require_matching_user(request, user_id)
    try:
        uid = int(user_id)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Invalid user id.") from exc
    if uid <= 0:
        raise HTTPException(status_code=400, detail="Invalid user id.")

    # Best-effort wipe (sign-out / reset for testing). Do not fail the request if
    # one step is already gone — the browser will clear local state regardless.
    try:
        purge_user_storage(uid)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:  # noqa: BLE001
        logger.exception("purge_user_storage failed for user %s", uid)

    try:
        delete_all_for_user(uid)
    except Exception:  # noqa: BLE001
        logger.exception("delete_all_for_user failed for user %s", uid)

    if not delete_user_by_id(uid):
        logger.info("delete_user_data: no SQLite row for user %s (memory may still be cleared)", uid)

    return {"success": True}
