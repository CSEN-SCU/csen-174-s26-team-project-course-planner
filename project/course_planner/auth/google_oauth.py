"""Google OAuth 2.0 (authorization code) helpers for Streamlit sign-in.

Confidential web client + server-side ID token verification. Does not use
the deprecated ``platform.js`` / ``gapi.auth2`` browser library. Never
persists access or refresh tokens — this flow is sign-in only.

Security model
--------------
- ``state``  is a CSRF token bound to a single sign-in attempt. Caller
  generates it, stores it server-side (``st.session_state``), passes it
  to :func:`build_authorization_url`, and must hand the same value to
  :func:`exchange_code_for_id_token`.
- ``nonce`` is an OIDC anti-replay value bound to a single sign-in
  attempt. Same lifecycle as ``state``. Verified against the ID token's
  ``nonce`` claim.
- The ID token is verified via Google's well-known keys
  (``id_token.verify_oauth2_token`` checks ``iss``, ``aud``, ``exp``,
  signature). We additionally check ``sub``, ``email``,
  ``email_verified``, optional ``hd`` / email-domain restriction, and
  ``nonce``.
"""

from __future__ import annotations

import logging
import os
import secrets
from typing import Any, Optional
from urllib.parse import urlparse

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from google_auth_oauthlib.flow import Flow

logger = logging.getLogger(__name__)

_OAUTH_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
]

_DEFAULT_REDIRECT_URI = "http://localhost:8501/"


class OAuthConfigError(RuntimeError):
    """Raised when GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET / redirect URI are unusable."""


class OAuthStateError(ValueError):
    """Raised on state/nonce/CSRF mismatch (treat as user-visible)."""


class OAuthClaimsError(ValueError):
    """Raised when ID token claims don't satisfy our sign-in policy."""


def google_oauth_configured() -> bool:
    return bool(_env("GOOGLE_CLIENT_ID") and _env("GOOGLE_CLIENT_SECRET"))


def get_redirect_uri() -> str:
    uri = _env("GOOGLE_OAUTH_REDIRECT_URI") or _DEFAULT_REDIRECT_URI
    parsed = urlparse(uri)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise OAuthConfigError(
            "GOOGLE_OAUTH_REDIRECT_URI must be an absolute http(s) URL."
        )
    return uri


def get_client_id() -> str:
    return _env("GOOGLE_CLIENT_ID")


def _env(key: str) -> str:
    return os.environ.get(key, "").strip()


def _client_config() -> dict[str, Any]:
    cid = _env("GOOGLE_CLIENT_ID")
    secret = _env("GOOGLE_CLIENT_SECRET")
    if not cid or not secret:
        raise OAuthConfigError(
            "GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set for Google sign-in."
        )
    return {
        "web": {
            "client_id": cid,
            "client_secret": secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }


def _new_flow() -> Flow:
    return Flow.from_client_config(
        _client_config(),
        scopes=_OAUTH_SCOPES,
        redirect_uri=get_redirect_uri(),
    )


def build_authorization_url(state: str, nonce: str) -> str:
    """Return Google's authorization URL bound to (``state``, ``nonce``).

    Both values must be high-entropy, single-use, and stored in
    ``st.session_state`` until the redirect comes back. The caller is
    responsible for regenerating them after every successful or failed
    exchange so the URL is not replayable.

    ``access_type='online'`` is intentional: we do not want refresh
    tokens since this flow is identity-only.
    """
    if not state or not nonce:
        raise OAuthStateError("state and nonce must be non-empty.")
    flow = _new_flow()
    url, _ = flow.authorization_url(
        state=state,
        nonce=nonce,
        access_type="online",
        prompt="select_account",
    )
    return url


def exchange_code_for_id_token(
    expected_state: str,
    query_state: str,
    code: str,
    *,
    expected_nonce: Optional[str] = None,
) -> dict[str, Any]:
    """Exchange an authorization ``code`` for verified ID token claims.

    Raises :class:`OAuthStateError` if state/nonce don't match, and
    :class:`OAuthClaimsError` if the token is malformed. The Google
    library raises its own errors for signature/expiry/audience problems;
    callers should treat any exception here as a hard failure and force
    the user back through the consent screen with a fresh state/nonce.
    """
    if not expected_state or not query_state:
        raise OAuthStateError("Missing OAuth state. Try signing in again.")
    if not secrets.compare_digest(expected_state, query_state):
        raise OAuthStateError("Invalid or expired OAuth state. Try signing in again.")
    if not code:
        raise OAuthStateError("Missing authorization code from Google.")

    flow = _new_flow()
    flow.fetch_token(code=code)
    creds = flow.credentials
    raw_id = getattr(creds, "id_token", None)
    if not isinstance(raw_id, str) or not raw_id:
        raise OAuthClaimsError("Google did not return an ID token.")

    claims = id_token.verify_oauth2_token(
        raw_id,
        google_requests.Request(),
        audience=get_client_id(),
    )

    if expected_nonce is not None:
        got_nonce = claims.get("nonce")
        if not isinstance(got_nonce, str) or not secrets.compare_digest(
            expected_nonce, got_nonce
        ):
            raise OAuthStateError("ID token nonce did not match the sign-in attempt.")

    return claims


def _allowed_domain() -> str:
    return _env("GOOGLE_OAUTH_ALLOWED_DOMAIN").lower()


def claims_after_domain_check(claims: dict[str, Any]) -> dict[str, Any]:
    """Apply optional ``GOOGLE_OAUTH_ALLOWED_DOMAIN`` (e.g. ``scu.edu``).

    Workspace organizations are gated via the ``hd`` claim when present;
    we fall back to the email suffix only for non-Workspace accounts so
    consumer Gmail users can never spoof their way into an org-gated
    deployment.
    """
    domain = _allowed_domain()
    if not domain:
        return claims
    email = (claims.get("email") or "").strip().lower()
    if "@" not in email:
        raise OAuthClaimsError("Google did not return a valid email.")
    hd = (claims.get("hd") or "").strip().lower()
    if hd:
        if hd != domain:
            raise OAuthClaimsError(f"Sign-in is restricted to @{domain} accounts.")
    elif not email.endswith(f"@{domain}"):
        raise OAuthClaimsError(f"Sign-in is restricted to @{domain} accounts.")
    return claims


def validate_sign_in_claims(claims: dict[str, Any]) -> dict[str, Any]:
    """Require ``sub``, verified ``email``, and any configured domain rule.

    Returns the (possibly filtered) claims dict on success. Caller should
    treat the result as the authoritative identity for this sign-in.
    """
    sub = claims.get("sub")
    if not isinstance(sub, str) or not sub:
        raise OAuthClaimsError("Google did not return a user id (sub).")
    email = (claims.get("email") or "").strip()
    if not email:
        raise OAuthClaimsError("Google did not return an email address.")
    if claims.get("email_verified") is not True:
        raise OAuthClaimsError("Google email must be verified to sign in.")
    return claims_after_domain_check(claims)


def display_name_from_claims(claims: dict[str, Any]) -> str:
    """Pick a human-friendly display name from the ID token.

    Order: ``name`` → ``given_name`` → email local part. Never trust the
    ID token for trust decisions — only for display.
    """
    for key in ("name", "given_name"):
        v = claims.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    email = (claims.get("email") or "").strip()
    if "@" in email:
        return email.split("@", 1)[0]
    return ""
