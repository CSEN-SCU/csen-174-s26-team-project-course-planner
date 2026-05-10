"""Streamlit-side login/registration glue.

Wraps `streamlit_authenticator.Authenticate` with a SQLite-backed
credentials provider, exposes `require_login()` to gate the rest of the
app, and clears all user-scoped session keys on logout.

This module is the only place that touches `st.session_state` for auth.
"""

from __future__ import annotations

import os
from typing import Optional

import streamlit as st
import streamlit_authenticator as stauth

from auth import users_db
from db.migrate import migrate

COOKIE_NAME = "scu_planner_session"
COOKIE_EXPIRY_DAYS = 7

# Cache key for the per-script-run Authenticate singleton. streamlit-
# authenticator's underlying CookieManager registers a fixed Streamlit
# component instance at construction time, so creating two Authenticates
# in the same run raises StreamlitDuplicateElementKey('init'). We work
# around that by stashing one Authenticate on session_state and reusing
# it everywhere within `streamlit_auth`.
_AUTH_SESSION_KEY = "_scu_authenticator"

# These keys are written by the planner main flow and must be cleared on
# logout so user A cannot leak state into user B's next session.
_USER_SCOPED_SESSION_KEYS = (
    "missing_details",
    "planning_result",
    "enriched_courses",
    "_recommended_enrichment_fp",
    "course_schedule_map",
    "calendar_replace_verify",
    "user_id",
    "username",
    "planning_user_preference",
    "last_planning_message",
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


def require_login() -> Optional[dict]:
    """Render login/register UI and return the current user dict or None.

    The caller is expected to `st.stop()` if this returns None so that no
    other UI for protected features renders. The Authenticate instance is
    cached in session_state so other helpers in this module (and the
    sidebar `logout_button`) can reuse it without re-constructing the
    underlying CookieManager.
    """
    migrate()

    authenticator = _get_authenticator()

    login_tab, register_tab = st.tabs(["Login", "Register"])

    with login_tab:
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

    # Authenticated: keep st.session_state['user_id'] in sync so the rest of
    # the app can scope all data by user_id.
    username = st.session_state.get("username")
    if not username:
        return None
    user = users_db.get_user_by_username(username)
    if user is None:
        # User was deleted while their cookie was still valid.
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
                # Logout helpers in some auth lib versions raise if no session.
                pass
        clear_user_scoped_session()
        # Drop the cached Authenticate so the next run starts cleanly.
        _invalidate_authenticator()
        st.rerun()
