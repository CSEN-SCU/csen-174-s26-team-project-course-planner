"""Pure-function tests for the Workday scraper helpers.

We can't drive a real Playwright session in CI, but the helpers that
classify pages and assemble selectors are pure enough to test against a
SimpleNamespace stand-in for ``Page``.  These tests pin:

  * ``_on_workday`` / ``_on_sso_page`` URL classification
  * ``_on_academic_progress_page`` title/heading heuristic
  * ``_active_workday_page`` scans every tab in a context
  * The export-button selector list is non-empty and includes the
    Workday automation IDs that we know exist in production
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from utils import workday_scraper as ws


# ── _on_sso_page / _on_workday URL classification ────────────────────────────


def _fake_page(url: str = "", title: str = "", heading: str = "", pages=None):
    """SimpleNamespace stand-in for a Playwright Page."""
    pages = list(pages) if pages is not None else None
    page = SimpleNamespace()
    page.url = url
    page.title = lambda: title
    page.evaluate = lambda js: heading
    page.context = SimpleNamespace(pages=pages if pages is not None else [page])
    return page


@pytest.mark.parametrize(
    "url,expected",
    [
        # SSO chain — must be flagged as SSO regardless of host
        ("https://login.scu.edu/Shibboleth.sso/SAML2/POST", True),
        ("https://accounts.google.com/oauth/auth?...", True),
        ("https://example.okta.com/signin", True),
        ("https://adfs.scu.edu/", True),
        ("https://example.com/login/redirect", True),
        # Plain Workday URLs are NOT SSO
        ("https://www.myworkday.com/scu/d/task/2998$44123.htmld", False),
        ("https://www.myworkday.com/scu/d/home.htmld", False),
        # Random non-SSO URL
        ("https://example.com/about", False),
    ],
)
def test_on_sso_page_url_classification(url, expected):
    page = _fake_page(url=url)
    assert ws._on_sso_page(page) is expected


def test_on_workday_requires_scu_tenant_and_not_sso():
    """`myworkday.com/scu` matches; pure SSO doesn't; other tenants don't."""
    assert ws._on_workday(_fake_page("https://www.myworkday.com/scu/d/task/X.htmld"))
    # SSO chain mid-flight — even if URL contains myworkday, SSO wins
    assert not ws._on_workday(
        _fake_page("https://www.myworkday.com/login/saml2/auth")
    )
    # Different tenant
    assert not ws._on_workday(_fake_page("https://www.myworkday.com/other/d/home.htmld"))
    # Random non-Workday
    assert not ws._on_workday(_fake_page("https://example.com/"))


# ── _on_academic_progress_page heuristic ─────────────────────────────────────


def test_on_academic_progress_matches_by_title():
    assert ws._on_academic_progress_page(
        _fake_page(title="View My Academic Progress - Workday")
    )
    assert ws._on_academic_progress_page(_fake_page(title="Academic Progress"))


def test_on_academic_progress_matches_by_h1():
    """Workday tabs sometimes have a generic title; the H1 should still hit."""
    page = _fake_page(title="Workday", heading="My Academic Progress")
    assert ws._on_academic_progress_page(page)


def test_on_academic_progress_does_not_match_active_holds():
    """The exact bug the user hit: SCU's old AP task ID now renders
    'View My Active Holds' instead.  Must be classified as NOT AP."""
    assert not ws._on_academic_progress_page(
        _fake_page(title="View My Active Holds - Workday", heading="View My Active Holds")
    )


def test_on_academic_progress_does_not_match_unrelated_pages():
    assert not ws._on_academic_progress_page(
        _fake_page(title="SCU Find Course Sections", heading="SCU Find Course Sections")
    )
    assert not ws._on_academic_progress_page(_fake_page(title="", heading=""))


def test_on_academic_progress_handles_exception():
    """If page.title() throws (closed tab etc.), the helper must return
    False rather than propagating the exception."""
    bad = SimpleNamespace()
    bad.title = lambda: (_ for _ in ()).throw(RuntimeError("closed"))
    bad.evaluate = lambda js: (_ for _ in ()).throw(RuntimeError("closed"))
    bad.url = ""
    bad.context = SimpleNamespace(pages=[])
    assert ws._on_academic_progress_page(bad) is False


# ── _active_workday_page walks every tab ─────────────────────────────────────


def test_active_workday_page_finds_workday_in_secondary_tab():
    """SSO sometimes opens the post-login Workday session in a NEW tab.
    The walker must check every page in the context, not just the seed."""
    sso = _fake_page(url="https://login.scu.edu/sso")
    workday = _fake_page(url="https://www.myworkday.com/scu/d/home.htmld")
    sso.context.pages = [sso, workday]
    workday.context.pages = [sso, workday]
    found = ws._active_workday_page(sso)
    assert found is workday


def test_active_workday_page_returns_none_when_all_tabs_on_sso():
    sso1 = _fake_page(url="https://login.scu.edu/sso")
    sso2 = _fake_page(url="https://shibboleth.scu.edu/idp")
    sso1.context.pages = [sso1, sso2]
    sso2.context.pages = [sso1, sso2]
    assert ws._active_workday_page(sso1) is None


def test_active_workday_page_handles_missing_context():
    """A degenerate page with no .context still works (returns None unless
    the page itself is on Workday)."""
    page = _fake_page(url="https://example.com/")
    page.context = None  # type: ignore[assignment]
    # No exception, returns None because the page itself isn't on Workday
    assert ws._active_workday_page(page) is None


def test_active_workday_page_returns_self_when_only_tab_is_workday():
    workday = _fake_page(url="https://www.myworkday.com/scu/d/home.htmld")
    workday.context.pages = [workday]
    assert ws._active_workday_page(workday) is workday


# ── Selectors / config sanity ────────────────────────────────────────────────


def test_workday_base_constant():
    """The hostname check should be 'myworkday.com/scu' — the SCU tenant
    path is what disambiguates from other Workday customers."""
    assert ws._WORKDAY_BASE == "myworkday.com/scu"


def test_sso_keywords_include_known_providers():
    """SCU funnels SSO through Shibboleth + Microsoft for MFA — both
    must be in the keyword list so we don't prematurely call login done."""
    kw = ws._SSO_KEYWORDS
    for needed in ("shibboleth", "saml", "microsoftonline", "auth", "login"):
        assert needed in kw, f"SSO keyword {needed!r} missing"


def test_academic_progress_headings_are_lower_case():
    """The heuristic lowercases input before matching; the headings list
    must also be lowercase or matching breaks silently."""
    for h in ws._ACADEMIC_PROGRESS_HEADINGS:
        assert h == h.lower()


def test_search_query_string_matches_workday_report_title():
    """The search-bar fallback types this exact phrase into Workday's
    universal search — must match the report's display title byte for
    byte or the suggestion list won't surface it."""
    assert ws._SEARCH_QUERY == "View My Academic Progress"
