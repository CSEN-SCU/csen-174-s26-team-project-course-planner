"""Stateless OAuth state/nonce/PKCE helpers, shared by Streamlit + FastAPI.

The browser navigates away to Google and back during sign-in. Anything
stored in a Streamlit ``session_state`` or a per-process FastAPI dict
will not survive that round-trip reliably. Instead we derive everything
the callback needs from the ``state`` query parameter itself, using
HMAC over a server-side signing key.

``state``         = ``"<rand>.<ts>.<hmac_hex>"`` — CSRF token.
``nonce``         = ``HMAC(key, "nonce:" + rand)`` — OIDC replay guard.
``code_verifier`` = ``HMAC(key, "pkce:"  + rand)`` — PKCE binding.

The callback parses ``state`` from the URL, verifies the HMAC, and
re-derives the matching nonce + verifier. No per-attempt server state
is kept.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from typing import Tuple

# Maximum lifetime of a signed OAuth state token. The full Google flow
# (consent screen + redirect) should complete in well under this; tokens
# older than this are rejected.
OAUTH_STATE_MAX_AGE_SEC = 600


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _hmac(key: bytes, data: str) -> bytes:
    return hmac.new(key, data.encode("ascii"), hashlib.sha256).digest()


def derive_nonce(rand: str, signing_key: bytes) -> str:
    return _b64url(_hmac(signing_key, f"nonce:{rand}"))


def derive_code_verifier(rand: str, signing_key: bytes) -> str:
    """PKCE verifier: 43-char URL-safe base64 of HMAC(key, "pkce:" + rand).

    Within RFC 7636's allowed alphabet ([A-Za-z0-9._~-]) and length
    (43–128). Recoverable from ``rand`` alone so the callback rebuilds
    it without persisting any per-attempt state.
    """
    return _b64url(_hmac(signing_key, f"pkce:{rand}"))


def mint_oauth_challenge(signing_key: bytes) -> Tuple[str, str, str]:
    """Return a fresh ``(state, nonce, code_verifier)`` tuple."""
    rand = secrets.token_urlsafe(24)
    ts = str(int(time.time()))
    sig = hmac.new(signing_key, f"{rand}.{ts}".encode("ascii"), hashlib.sha256).hexdigest()
    state = f"{rand}.{ts}.{sig}"
    return state, derive_nonce(rand, signing_key), derive_code_verifier(rand, signing_key)


def verify_state_and_derive_secrets(
    state: str,
    signing_key: bytes,
    *,
    max_age_sec: int = OAUTH_STATE_MAX_AGE_SEC,
) -> Tuple[str, str]:
    """Verify the signed state token and return ``(nonce, code_verifier)``.

    Raises :class:`ValueError` with a user-safe message on any tamper /
    format / expiry failure. Callers should treat any exception here as
    a hard failure and force the user back through the consent screen.
    """
    if not state:
        raise ValueError("Missing OAuth state.")
    parts = state.split(".")
    if len(parts) != 3:
        raise ValueError("Invalid OAuth state format.")
    rand, ts_str, sig = parts
    try:
        ts = int(ts_str)
    except ValueError as exc:
        raise ValueError("Invalid OAuth state timestamp.") from exc
    expected_sig = hmac.new(
        signing_key, f"{rand}.{ts_str}".encode("ascii"), hashlib.sha256
    ).hexdigest()
    if not secrets.compare_digest(sig, expected_sig):
        raise ValueError("Invalid OAuth state signature.")
    now = int(time.time())
    if now - ts > max_age_sec or ts - now > 60:
        raise ValueError("OAuth state expired. Try signing in again.")
    return derive_nonce(rand, signing_key), derive_code_verifier(rand, signing_key)
