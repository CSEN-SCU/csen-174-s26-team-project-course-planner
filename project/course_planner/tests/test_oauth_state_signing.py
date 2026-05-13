"""Tests for the stateless HMAC-signed OAuth state used by streamlit_auth.

The Streamlit redirect to Google drops ``st.session_state``, so the
state and nonce must round-trip through Google's URL and be verifiable
from the returned ``state`` alone.
"""

from __future__ import annotations

import time

import pytest


@pytest.fixture(autouse=True)
def _fixed_cookie_key(monkeypatch):
    monkeypatch.setenv("SCU_PLANNER_COOKIE_KEY", "test-signing-key-please-rotate")
    yield


def test_mint_and_verify_roundtrip():
    from auth import streamlit_auth

    state, nonce, verifier = streamlit_auth._mint_oauth_challenge()
    assert state.count(".") == 2, "state must be three dot-separated parts"
    assert nonce, "nonce must be non-empty"
    # PKCE verifier must be 43-128 chars of [A-Za-z0-9._~-] per RFC 7636.
    assert 43 <= len(verifier) <= 128
    assert all(c.isalnum() or c in "._~-" for c in verifier)

    n2, v2 = streamlit_auth._verify_oauth_state_and_derive_secrets(state)
    assert n2 == nonce, "callback must recover the same nonce from state alone"
    assert v2 == verifier, "callback must recover the same PKCE verifier"


def test_two_mints_produce_distinct_states():
    from auth import streamlit_auth

    s1, n1, v1 = streamlit_auth._mint_oauth_challenge()
    s2, n2, v2 = streamlit_auth._mint_oauth_challenge()
    assert s1 != s2
    assert n1 != n2
    assert v1 != v2


def test_tampered_state_rejected():
    from auth import streamlit_auth

    state, _, _ = streamlit_auth._mint_oauth_challenge()
    rand, ts, sig = state.split(".")
    tampered = f"{rand}.{ts}.{'0' * len(sig)}"
    with pytest.raises(ValueError, match="signature"):
        streamlit_auth._verify_oauth_state_and_derive_secrets(tampered)


def test_state_signed_by_different_key_rejected(monkeypatch):
    from auth import streamlit_auth

    state, _, _ = streamlit_auth._mint_oauth_challenge()
    monkeypatch.setenv("SCU_PLANNER_COOKIE_KEY", "a-completely-different-key")
    with pytest.raises(ValueError, match="signature"):
        streamlit_auth._verify_oauth_state_and_derive_secrets(state)


def test_expired_state_rejected(monkeypatch):
    from auth import oauth_state, streamlit_auth

    real_time = time.time
    monkeypatch.setattr(oauth_state.time, "time", lambda: real_time() - 3600)
    old_state, _, _ = streamlit_auth._mint_oauth_challenge()
    monkeypatch.setattr(oauth_state.time, "time", real_time)
    with pytest.raises(ValueError, match="expired"):
        streamlit_auth._verify_oauth_state_and_derive_secrets(old_state)


def test_malformed_state_rejected():
    from auth import streamlit_auth

    for bad in ("", "no-dots-here", "only.two.dots.too.many", "rand.notanint.sig"):
        with pytest.raises(ValueError):
            streamlit_auth._verify_oauth_state_and_derive_secrets(bad)
