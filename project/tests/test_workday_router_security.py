"""Workday router security hardening (red-team finding #3).

Pins the post-hardening behaviour of `project/api/routers/workday.py`:

  * URL allowlist drops non-SCU / non-HTTPS / `javascript:` / `file://`
    URLs so the Playwright scraper never goto()s an attacker-controlled
    host (SSRF prevention).
  * `_scrub_error` maps known exception classes to curated user-facing
    strings and never returns the raw exception message — internal
    paths / module names stay out of the UI.
  * `_require_user` returns 401 for missing / non-numeric / invalid user
    ids (no auth-by-string-spoofing).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

_API = Path(__file__).resolve().parents[2] / "api"
if str(_API) not in sys.path:
    sys.path.insert(0, str(_API))

from routers.workday import (  # noqa: E402
    _GENERIC_ERROR,
    _require_user,
    _scrub_error,
    _validated_workday_url,
)


# ── URL allowlist ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "url",
    [
        "https://www.myworkday.com/scu/d/task/2998$44123.htmld",
        "https://wd5.myworkday.com/scu/d/home.htmld",
        "https://myworkday.com/scu/d/task/X.htmld",
    ],
)
def test_allowlist_accepts_scu_workday_urls(url):
    assert _validated_workday_url(url) == url


@pytest.mark.parametrize(
    "url",
    [
        # Non-SCU tenant
        "https://www.myworkday.com/other-school/d/home.htmld",
        # Random host
        "https://evil.example.com/scu/x",
        # Different scheme
        "javascript:alert(1)",
        "file:///etc/passwd",
        "data:text/html,<script>",
        "http://www.myworkday.com/scu/d/X.htmld",  # plain http rejected
        # Garbage
        "",
        "   ",
        "not-a-url",
        "ftp://www.myworkday.com/scu/",
    ],
)
def test_allowlist_rejects_everything_else(url):
    assert _validated_workday_url(url) is None


def test_allowlist_rejects_non_string():
    assert _validated_workday_url(None) is None  # type: ignore[arg-type]
    assert _validated_workday_url(12345) is None  # type: ignore[arg-type]
    assert _validated_workday_url([]) is None  # type: ignore[arg-type]


# ── Error scrubbing ──────────────────────────────────────────────────────────


def test_scrub_timeout_says_login_timed_out():
    """The synchronous scraper raises plain TimeoutError for SSO/login
    expiry — UI should say so without leaking the message text."""
    msg = _scrub_error(TimeoutError("internal /Users/foo/secret/path"))
    assert "Login timed out" in msg
    assert "/Users/" not in msg


def test_scrub_module_not_found_says_not_enabled():
    msg = _scrub_error(ModuleNotFoundError("No module named 'playwright'"))
    assert "not enabled" in msg.lower()
    assert "playwright" not in msg.lower()  # no module name leakage


def test_scrub_generic_exception_returns_generic_message():
    msg = _scrub_error(RuntimeError("stack: /usr/local/lib/secret.py:42 KEY=xyz"))
    assert msg == _GENERIC_ERROR
    assert "/usr/local" not in msg
    assert "KEY=xyz" not in msg


def test_scrub_value_error_still_safe():
    msg = _scrub_error(ValueError("session token sk-12345"))
    assert "sk-12345" not in msg


# ── Auth gate ─────────────────────────────────────────────────────────────────


def test_require_user_empty_raises_401():
    with pytest.raises(HTTPException) as exc:
        _require_user("")
    assert exc.value.status_code == 401


def test_require_user_whitespace_raises_401():
    with pytest.raises(HTTPException) as exc:
        _require_user("   ")
    assert exc.value.status_code == 401


def test_require_user_none_raises_401():
    with pytest.raises(HTTPException) as exc:
        _require_user(None)
    assert exc.value.status_code == 401


def test_require_user_nonexistent_id_raises_401(monkeypatch):
    """A syntactically-valid id that does not resolve to a real row is 401."""
    import routers.workday as wd

    monkeypatch.setattr(wd, "get_user_by_id", lambda uid: None)
    with pytest.raises(HTTPException) as exc:
        _require_user("99999")
    assert exc.value.status_code == 401


def test_require_user_valid_returns_canonical_id(monkeypatch):
    import routers.workday as wd

    monkeypatch.setattr(
        wd, "get_user_by_id", lambda uid: {"id": 42, "username": "alice"}
    )
    assert _require_user("42") == "42"
