"""Regression test: streamlit_auth must build at most one Authenticate per run.

streamlit-authenticator 0.4.x's Authenticate constructor instantiates a
``CookieManager`` whose underlying Streamlit component registers a
fixed element key (``'init'``). Constructing it twice in the same script
run raises ``StreamlitDuplicateElementKey``, which previously crashed
the app on the first authenticated render (require_login + logout_button
each tried to build their own).

These tests pin the singleton/caching behavior so the bug cannot return.
"""

from __future__ import annotations

import pytest


@pytest.fixture()
def stub_session_state(monkeypatch):
    import streamlit as st

    state: dict = {}
    monkeypatch.setattr(st, "session_state", state)
    return state


def test_get_authenticator_caches_after_first_build(monkeypatch, stub_session_state):
    from auth import streamlit_auth

    build_calls: list[int] = []

    class _FakeAuth:
        def __init__(self, marker):
            self.marker = marker

    def fake_build():
        build_calls.append(1)
        return _FakeAuth(marker=len(build_calls))

    monkeypatch.setattr(streamlit_auth, "_build_authenticator", fake_build)

    a = streamlit_auth._get_authenticator()
    b = streamlit_auth._get_authenticator()
    c = streamlit_auth._get_authenticator()

    assert a is b is c, "Authenticate must be a singleton across calls in one run"
    assert len(build_calls) == 1, (
        "Expected exactly one underlying construction; got %d (this would "
        "trigger StreamlitDuplicateElementKey('init') in the live app)"
        % len(build_calls)
    )


def test_invalidate_authenticator_forces_rebuild(monkeypatch, stub_session_state):
    from auth import streamlit_auth

    build_calls: list[int] = []
    monkeypatch.setattr(
        streamlit_auth,
        "_build_authenticator",
        lambda: (build_calls.append(1), object())[1],
    )

    first = streamlit_auth._get_authenticator()
    streamlit_auth._invalidate_authenticator()
    second = streamlit_auth._get_authenticator()

    assert first is not second
    assert len(build_calls) == 2


def test_logout_button_uses_cached_authenticator_only(monkeypatch, stub_session_state):
    """`logout_button` must never call `_build_authenticator` itself.

    If it did, an authenticated render (require_login already built one)
    would construct a second CookieManager and crash.
    """
    from auth import streamlit_auth

    rebuilds: list[int] = []
    monkeypatch.setattr(
        streamlit_auth,
        "_build_authenticator",
        lambda: rebuilds.append(1) or object(),
    )

    cached = object()
    stub_session_state[streamlit_auth._AUTH_SESSION_KEY] = cached

    # Stub the Streamlit primitives logout_button touches so we don't need
    # a real Streamlit runtime.
    import streamlit as st

    sidebar_calls: dict = {}
    monkeypatch.setattr(
        st,
        "sidebar",
        type(
            "_FakeSidebar",
            (),
            {"button": staticmethod(lambda *a, **kw: sidebar_calls.setdefault("called", True) and False or False)},
        )(),
    )

    streamlit_auth.logout_button()

    assert rebuilds == [], (
        "logout_button must reuse the cached Authenticate; building a new "
        "one in the same script run causes StreamlitDuplicateElementKey."
    )
