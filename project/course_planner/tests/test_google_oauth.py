"""Unit tests for auth/google_oauth.py (no network)."""

from __future__ import annotations

import pytest


@pytest.fixture()
def oauth_env(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "cid.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "s")
    monkeypatch.setenv("GOOGLE_OAUTH_REDIRECT_URI", "http://localhost:8501/")
    monkeypatch.delenv("GOOGLE_OAUTH_ALLOWED_DOMAIN", raising=False)


def test_google_oauth_configured_requires_both_ids(monkeypatch):
    from auth import google_oauth

    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
    assert google_oauth.google_oauth_configured() is False

    monkeypatch.setenv("GOOGLE_CLIENT_ID", "x.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "")
    assert google_oauth.google_oauth_configured() is False

    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "secret")
    assert google_oauth.google_oauth_configured() is True


def test_redirect_uri_rejects_non_http(monkeypatch):
    from auth import google_oauth

    monkeypatch.setenv("GOOGLE_OAUTH_REDIRECT_URI", "javascript:alert(1)")
    with pytest.raises(google_oauth.OAuthConfigError):
        google_oauth.get_redirect_uri()


def test_exchange_code_rejects_state_mismatch(oauth_env):
    from auth import google_oauth

    with pytest.raises(google_oauth.OAuthStateError, match="Invalid or expired"):
        google_oauth.exchange_code_for_id_token("expected", "different", "fake-code")


def test_exchange_code_rejects_missing_state(oauth_env):
    from auth import google_oauth

    with pytest.raises(google_oauth.OAuthStateError, match="Missing OAuth state"):
        google_oauth.exchange_code_for_id_token("", "anything", "fake-code")


def test_exchange_code_rejects_empty_code(oauth_env):
    from auth import google_oauth

    with pytest.raises(google_oauth.OAuthStateError, match="Missing authorization code"):
        google_oauth.exchange_code_for_id_token("s", "s", "")


def test_validate_sign_in_claims_requires_verified_email(monkeypatch):
    from auth import google_oauth

    monkeypatch.delenv("GOOGLE_OAUTH_ALLOWED_DOMAIN", raising=False)
    with pytest.raises(google_oauth.OAuthClaimsError, match="verified"):
        google_oauth.validate_sign_in_claims(
            {"sub": "1", "email": "a@b.com", "email_verified": False}
        )

    out = google_oauth.validate_sign_in_claims(
        {"sub": "1", "email": "a@b.com", "email_verified": True}
    )
    assert out["email"] == "a@b.com"


def test_validate_sign_in_claims_requires_sub(monkeypatch):
    from auth import google_oauth

    monkeypatch.delenv("GOOGLE_OAUTH_ALLOWED_DOMAIN", raising=False)
    with pytest.raises(google_oauth.OAuthClaimsError, match="user id"):
        google_oauth.validate_sign_in_claims(
            {"email": "a@b.com", "email_verified": True}
        )


def test_claims_after_domain_check_email_suffix(monkeypatch):
    from auth import google_oauth

    monkeypatch.setenv("GOOGLE_OAUTH_ALLOWED_DOMAIN", "scu.edu")
    # No hd claim → fall back to email suffix.
    claims = {"sub": "9", "email": "stu@scu.edu", "email_verified": True}
    assert google_oauth.claims_after_domain_check(claims) == claims

    with pytest.raises(google_oauth.OAuthClaimsError, match="restricted"):
        google_oauth.claims_after_domain_check(
            {"sub": "9", "email": "x@gmail.com", "email_verified": True}
        )


def test_claims_after_domain_check_hd_claim_preferred(monkeypatch):
    from auth import google_oauth

    monkeypatch.setenv("GOOGLE_OAUTH_ALLOWED_DOMAIN", "scu.edu")
    # hd claim mismatches even if email happens to end in @scu.edu.
    with pytest.raises(google_oauth.OAuthClaimsError, match="restricted"):
        google_oauth.claims_after_domain_check(
            {
                "sub": "9",
                "email": "shadow@scu.edu",
                "email_verified": True,
                "hd": "evil.example",
            }
        )

    # hd claim matches → pass.
    claims = {
        "sub": "9",
        "email": "stu@scu.edu",
        "email_verified": True,
        "hd": "scu.edu",
    }
    assert google_oauth.claims_after_domain_check(claims) == claims


def test_build_authorization_url_requires_state_and_nonce(oauth_env):
    from auth import google_oauth

    with pytest.raises(google_oauth.OAuthStateError):
        google_oauth.build_authorization_url("", "n")
    with pytest.raises(google_oauth.OAuthStateError):
        google_oauth.build_authorization_url("s", "")


def test_build_authorization_url_includes_state_and_nonce(oauth_env):
    from auth import google_oauth

    url = google_oauth.build_authorization_url("state-xyz", "nonce-abc")
    assert "state=state-xyz" in url
    assert "nonce=nonce-abc" in url
    assert "response_type=code" in url
    assert "client_id=cid.apps.googleusercontent.com" in url


def test_display_name_from_claims_prefers_name():
    from auth import google_oauth

    assert google_oauth.display_name_from_claims(
        {"name": "Ada Lovelace", "given_name": "Ada", "email": "ada@x.com"}
    ) == "Ada Lovelace"
    assert google_oauth.display_name_from_claims(
        {"given_name": "Ada", "email": "ada@x.com"}
    ) == "Ada"
    assert google_oauth.display_name_from_claims({"email": "ada@x.com"}) == "ada"
    assert google_oauth.display_name_from_claims({}) == ""
