"""Streamlit-side login/registration glue.

Wraps `streamlit_authenticator.Authenticate` with a SQLite-backed
credentials provider, exposes `require_login()` to gate the rest of the
app, and clears all user-scoped session keys on logout.

This module is the only place that touches `st.session_state` for auth.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Optional

import streamlit as st
import streamlit_authenticator as stauth

from auth import oauth_state, users_db
from db.migrate import migrate

try:
    from auth import google_oauth as _google_oauth
except ImportError:  # pragma: no cover - exercised only when google-auth wheels missing
    _google_oauth = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

COOKIE_NAME = "scu_planner_session"
COOKIE_EXPIRY_DAYS = 7

# Cache key for the per-script-run Authenticate singleton. streamlit-
# authenticator's underlying CookieManager registers a fixed Streamlit
# component instance at construction time, so creating two Authenticates
# in the same run raises StreamlitDuplicateElementKey('init'). We work
# around that by stashing one Authenticate on session_state and reusing
# it everywhere within `streamlit_auth`.
_AUTH_SESSION_KEY = "_scu_authenticator"

# Single source of truth for the session keys streamlit-authenticator
# writes. If the library renames any of these in a future version, the
# fix is here, not scattered across helpers.
_AUTHENTICATOR_SESSION_KEYS: tuple[str, ...] = (
    "authentication_status",
    "username",
    "name",
    "email",
)

# OAuth state and nonce are now stateless (HMAC-signed; recovered from the
# returned ``state`` query param). No session_state lifecycle to manage.
_OAUTH_SESSION_KEYS: tuple[str, ...] = ()

# These keys are written by the planner main flow and must be cleared on
# logout so user A cannot leak state into user B's next session.
_USER_SCOPED_SESSION_KEYS: tuple[str, ...] = (
    "missing_details",
    "parsed_rows",
    "transcript_progress_snapshot",
    "planning_result",
    "enriched_courses",
    "_recommended_enrichment_fp",
    "course_schedule_map",
    "calendar_replace_verify",
    "user_id",
    "planning_user_preference",
    "last_planning_message",
    *_AUTHENTICATOR_SESSION_KEYS,
    *_OAUTH_SESSION_KEYS,
)


def _cookie_key() -> str:
    """Get the signing key for the auth cookie.

    In production set `SCU_PLANNER_COOKIE_KEY`. In dev we fall back to a
    deterministic placeholder so the prototype runs without extra setup.
    """
    return os.environ.get("SCU_PLANNER_COOKIE_KEY", "dev-cookie-key-change-me")


def _build_authenticator() -> stauth.Authenticate:
    """Build a fresh Authenticate from the current users table."""
    credentials = users_db.get_credentials_dict()
    return stauth.Authenticate(
        credentials=credentials,
        cookie_name=COOKIE_NAME,
        cookie_key=_cookie_key(),
        cookie_expiry_days=COOKIE_EXPIRY_DAYS,
    )


def _get_authenticator() -> stauth.Authenticate:
    """Return the Authenticate singleton for this session, building it once.

    Construction has Streamlit-component side effects (CookieManager), so
    only the first call per session actually constructs; later calls
    (e.g. from `logout_button`) reuse the cached instance to avoid the
    ``StreamlitDuplicateElementKey('init')`` error.
    """
    cached = st.session_state.get(_AUTH_SESSION_KEY)
    if cached is None:
        cached = _build_authenticator()
        st.session_state[_AUTH_SESSION_KEY] = cached
    return cached


def _invalidate_authenticator() -> None:
    """Drop the cached Authenticate so the next run rebuilds it.

    Called after registering a new user so that the freshly inserted
    credentials become visible immediately, and after logout so the next
    sign-in starts from a clean state.
    """
    st.session_state.pop(_AUTH_SESSION_KEY, None)


def clear_user_scoped_session() -> None:
    """Remove every session_state key that should not survive a logout."""
    for key in list(st.session_state.keys()):
        if key in _USER_SCOPED_SESSION_KEYS:
            del st.session_state[key]


def _clear_oauth_query_params() -> None:
    """Remove OAuth-related parameters from the URL after a callback.

    Targets Google's documented redirect params plus error/error_description
    so a denied or expired auth doesn't leave noise in the address bar.
    """
    for key in ("code", "state", "scope", "authuser", "hd", "prompt",
                "error", "error_description", "error_uri"):
        if key in st.query_params:
            del st.query_params[key]


def _apply_authenticated_session(user: dict, *, display_name: str = "") -> None:
    """Mirror streamlit-authenticator session keys plus ``user_id``.

    Internal: only call this immediately after we have verified the
    identity via either a password check or a Google ID token.
    """
    st.session_state["authentication_status"] = True
    st.session_state["username"] = user["username"]
    st.session_state["name"] = display_name or user["username"]
    st.session_state["email"] = str(user.get("email") or "")
    st.session_state["user_id"] = int(user["id"])


def _sync_user_if_authenticated_in_session() -> Optional[dict]:
    """If session_state reflects a logged-in user, validate against DB and return user row."""
    if st.session_state.get("authentication_status") is not True:
        return None
    username = st.session_state.get("username")
    if not username:
        return None
    user = users_db.get_user_by_username(username)
    if user is None:
        return None
    st.session_state["user_id"] = int(user["id"])
    return user


def _oauth_signing_key() -> bytes:
    """Signing key for OAuth state tokens; reuses the cookie secret."""
    return _cookie_key().encode("utf-8")


def _mint_oauth_challenge() -> tuple[str, str, str]:
    """Thin wrapper around :func:`oauth_state.mint_oauth_challenge`."""
    return oauth_state.mint_oauth_challenge(_oauth_signing_key())


def _verify_oauth_state_and_derive_secrets(state: str) -> tuple[str, str]:
    """Thin wrapper around :func:`oauth_state.verify_state_and_derive_secrets`."""
    return oauth_state.verify_state_and_derive_secrets(state, _oauth_signing_key())


def _handle_google_error_redirect() -> bool:
    """If Google redirected with ``?error=...``, surface it and clean up.

    Returns ``True`` if it handled an error (caller should not try to
    process a code in the same run), ``False`` otherwise.
    """
    err = st.query_params.get("error")
    if not err:
        return False
    description = st.query_params.get("error_description") or ""
    if err == "access_denied":
        msg = "Google sign-in was cancelled."
    else:
        # Don't echo Google's full error_description into the UI verbatim
        # in production — log it instead and show a stable message.
        msg = "Google sign-in failed. Please try again."
    logger.warning("Google OAuth redirect error: %s %s", err, description)
    _clear_oauth_query_params()
    st.error(msg)
    return True


def _try_complete_google_oauth_callback() -> None:
    """Handle ``?code=&state=`` (or ``?error=``) on the redirect; reruns on success.

    Stateless: ``state`` is an HMAC-signed token that travels round-trip
    through Google. We verify the signature and re-derive the expected
    ``nonce`` rather than depending on ``st.session_state``, which
    Streamlit wipes during external navigation.
    """
    if _google_oauth is None or not _google_oauth.google_oauth_configured():
        return

    if _handle_google_error_redirect():
        return

    code = st.query_params.get("code")
    state_qp = st.query_params.get("state")
    if not code or not state_qp:
        return

    try:
        expected_nonce, code_verifier = _verify_oauth_state_and_derive_secrets(state_qp)
        raw = _google_oauth.exchange_code_for_id_token(
            state_qp,
            state_qp,
            code,
            expected_nonce=expected_nonce,
            code_verifier=code_verifier,
        )
        claims = _google_oauth.validate_sign_in_claims(raw)
        user = users_db.get_or_create_user_for_google(
            str(claims["email"]),
            str(claims["sub"]),
        )
        display_name = _google_oauth.display_name_from_claims(claims)
        _apply_authenticated_session(user, display_name=display_name)
        logger.info("Google OAuth sign-in succeeded for %s", claims.get("email"))
    except (_google_oauth.OAuthStateError, _google_oauth.OAuthClaimsError, ValueError) as exc:
        # Safe to show: these are user-facing policy errors we wrote ourselves.
        logger.warning("Google OAuth claim/state rejected: %s", exc)
        st.error(str(exc))
    except Exception:
        # Anything else (network, library, signature, expired token, DB) is
        # logged with a stack but not shown to the user.
        logger.exception("Google OAuth callback failed")
        st.error("Google sign-in failed. Please try again.")
    finally:
        _clear_oauth_query_params()
        _invalidate_authenticator()

    if st.session_state.get("authentication_status") is True:
        st.rerun()


def _render_register_tab() -> None:
    st.subheader("Create an account")
    with st.form("scu_planner_register"):
        username = st.text_input("Username", help="3-32 chars: letters, digits, ._-")
        email = st.text_input("Email")
        pw1 = st.text_input("Password", type="password")
        pw2 = st.text_input("Confirm password", type="password")
        submitted = st.form_submit_button("Register")
    if not submitted:
        return
    if pw1 != pw2:
        st.error("Passwords do not match.")
        return
    try:
        users_db.create_user(username, email, pw1)
    except users_db.UserAlreadyExistsError:
        st.error("That username or email is already taken.")
    except ValueError as exc:
        st.error(str(exc))
    else:
        # Force the next rerun to rebuild Authenticate so the new
        # credentials show up in its in-memory dict.
        _invalidate_authenticator()
        st.success("Account created. Switch to the Login tab to sign in.")


def _render_google_signin_button() -> None:
    """Render the ``Continue with Google`` link button with a fresh challenge.

    A fresh ``state`` and ``nonce`` are minted on every render so a single
    authorize URL is only ever valid for one attempt. The library
    raises :class:`google_oauth.OAuthConfigError` if env is misconfigured;
    we log and silently skip so the page still renders the password form.
    """
    if _google_oauth is None or not _google_oauth.google_oauth_configured():
        return
    try:
        state, nonce, code_verifier = _mint_oauth_challenge()
        auth_url = _google_oauth.build_authorization_url(
            state, nonce, code_verifier=code_verifier
        )
    except Exception:
        logger.exception("Failed to build Google authorization URL")
        st.warning("Google sign-in is temporarily unavailable.")
        return
    st.markdown("**Sign in with Google**")
    try:
        st.link_button("Continue with Google", auth_url, width="stretch")
    except TypeError:
        # Streamlit < 1.36: link_button has no `width` kwarg.
        st.link_button("Continue with Google", auth_url)
    st.divider()


def require_login() -> Optional[dict]:
    """Render login/register UI and return the current user dict or None.

    The caller is expected to `st.stop()` if this returns None so that no
    other UI for protected features renders. The Authenticate instance is
    cached in session_state so other helpers in this module (and the
    sidebar `logout_button`) can reuse it without re-constructing the
    underlying CookieManager.
    """
    migrate()

    _try_complete_google_oauth_callback()

    # Google-only sessions never get streamlit-authenticator cookies; resolve
    # them before ``login()`` so that call does not clear session_state.
    user_early = _sync_user_if_authenticated_in_session()
    if user_early is not None:
        _get_authenticator()
        return user_early

    authenticator = _get_authenticator()

    login_tab, register_tab = st.tabs(["Login", "Register"])

    with login_tab:
        _render_google_signin_button()
        try:
            authenticator.login(location="main")
        except stauth.LoginError as exc:
            st.error(str(exc))

    auth_status = st.session_state.get("authentication_status")

    if auth_status is False:
        with login_tab:
            st.error("Username or password is incorrect.")
    elif auth_status is None:
        with login_tab:
            st.info("Please log in or create an account to continue.")
        with register_tab:
            _render_register_tab()
        return None

    username = st.session_state.get("username")
    if not username:
        return None
    user = users_db.get_user_by_username(username)
    if user is None:
        authenticator.logout(location="unrendered")
        clear_user_scoped_session()
        return None

    st.session_state["user_id"] = int(user["id"])
    st.session_state["username"] = user["username"]
    return user


def logout_button(authenticator: Optional[stauth.Authenticate] = None) -> None:
    """Render a logout button in the sidebar that wipes user-scoped state.

    Reuses the cached Authenticate from `require_login()`; never builds a
    second one (that would crash with ``StreamlitDuplicateElementKey``
    because the underlying CookieManager registers a Streamlit component
    keyed `'init'`).
    """
    auth = authenticator or st.session_state.get(_AUTH_SESSION_KEY)
    if st.sidebar.button("Log out", key="scu_planner_logout"):
        if auth is not None:
            try:
                auth.logout(location="unrendered")
            except Exception:
                logger.debug("authenticator.logout raised on a stale session", exc_info=True)
        clear_user_scoped_session()
        _invalidate_authenticator()
        st.rerun()
