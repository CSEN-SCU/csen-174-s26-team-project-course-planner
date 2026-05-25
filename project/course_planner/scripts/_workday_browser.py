"""
Shared Playwright browser helper for the headed, human-authenticated Workday
pull scripts (``workday_pull_progress.py`` / ``workday_pull_sections.py``).

Safety model — the deliberate opposite of the removed ``c095321`` scraper:

  * **Headed** (visible) Chromium, never headless.
  * **The human logs in** — SSO + Duo MFA happen in the real browser window;
    this module never sees, asks for, or stores SCU credentials.
  * **Persistent profile** keeps the Workday session across runs (cookies live
    in a local, gitignored profile dir — never SCU passwords).
  * **No DOM scraping** of academic data: we click Workday's native
    *Export to Excel* control and capture the downloaded ``.xlsx`` bytes, which
    the existing parsers already understand.

Public API (the two pull scripts depend on these signatures)::

    context, page = launch(profile_dir)
    wait_for_login(page)                       # blocks until the human is in
    data = export_to_excel(page, navigate)     # navigate(page) -> task page

Selector lists are recovered from the removed ``utils/workday_scraper.py``
(``git show c095321``; export detection hardened in ``220e63a``).
"""

from __future__ import annotations

import tempfile
import time
from collections.abc import Callable
from pathlib import Path

from playwright.sync_api import (
    BrowserContext,
    Page,
    TimeoutError as PWTimeout,
    sync_playwright,
)

__all__ = ["launch", "wait_for_login", "export_to_excel"]

# ── Config ──────────────────────────────────────────────────────────────────

# Landing URL. Hitting the SCU tenant while unauthenticated triggers the
# Workday → SSO redirect, which is exactly the login flow we want the human to
# complete in the visible window.
WORKDAY_HOME = "https://www.myworkday.com/scu/d/home.htmld"

# The ``/scu`` tenant path disambiguates our Workday from every other customer.
WORKDAY_BASE = "myworkday.com/scu"

# Substrings that mark a mid-flight SSO/MFA page. SCU funnels login through
# Shibboleth + Microsoft (Duo), so a URL containing any of these means "still
# logging in" — even when the host is myworkday.com.
SSO_KEYWORDS = (
    "login", "sso", "saml", "oauth", "auth", "signin",
    "adfs", "okta", "microsoftonline", "shibboleth", "duosecurity", "duo",
)

NAV_TIMEOUT_MS = 60 * 1000
DL_TIMEOUT_MS = 90 * 1000
RENDER_WAIT_MS = 4_000  # fixed pause after navigation for the SPA to paint

_LOGIN_PROMPT = (
    "\n"
    "============================================================\n"
    " A Workday window just opened.\n"
    " Please LOG IN and approve the Duo (MFA) prompt in that window.\n"
    " This tool never sees your password — you authenticate yourself.\n"
    " Waiting for login to complete...\n"
    "============================================================\n"
)


# ── Page classification (login detection — URL only, no DOM scraping) ────────

def _on_sso_page(page: Page) -> bool:
    return any(kw in page.url.lower() for kw in SSO_KEYWORDS)


def _on_workday(page: Page) -> bool:
    return WORKDAY_BASE in page.url.lower() and not _on_sso_page(page)


def _active_workday_page(initial: Page) -> Page | None:
    """Return whichever tab in the context is on Workday (past SSO), or None.

    SSO can land the post-login session in a new tab, so we scan every page in
    the context rather than only the one we opened.
    """
    try:
        for p in initial.context.pages:
            if _on_workday(p):
                return p
    except Exception:  # noqa: BLE001 — closed/degenerate page → fall through
        pass
    return initial if _on_workday(initial) else None


def _wait_for_render(page: Page) -> None:
    """Wait for Workday content to paint.

    ``networkidle`` never fires on Workday (the SPA polls forever), so we wait
    for ``domcontentloaded`` plus a short fixed pause instead.
    """
    try:
        page.wait_for_load_state("domcontentloaded", timeout=30_000)
    except PWTimeout:
        pass
    page.wait_for_timeout(RENDER_WAIT_MS)


# ── Public: launch ───────────────────────────────────────────────────────────

def launch(profile_dir: str | Path) -> tuple[BrowserContext, Page]:
    """Open a headed Chromium with a persistent profile, parked on Workday.

    Uses ``launch_persistent_context`` so the Workday session (cookies) survives
    between runs — only the cookies, never credentials. ``profile_dir`` is
    created on first run. Returns ``(context, page)``; the caller is responsible
    for ``context.close()`` when done.
    """
    profile_path = Path(profile_dir)
    profile_path.mkdir(parents=True, exist_ok=True)  # first run creates it

    pw = sync_playwright().start()
    context = pw.chromium.launch_persistent_context(
        user_data_dir=str(profile_path),
        headless=False,            # never headless — the human must see + log in
        accept_downloads=True,     # required to capture the Export-to-Excel file
        no_viewport=True,
        args=["--start-maximized"],
    )
    # Keep the driver alive for the context's lifetime (caller closes context).
    context._playwright = pw  # type: ignore[attr-defined]

    page = context.pages[0] if context.pages else context.new_page()
    try:
        page.goto(WORKDAY_HOME, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
    except Exception:  # noqa: BLE001 — SSO redirect may interrupt load; that's fine
        pass
    return context, page


# ── Public: wait_for_login ───────────────────────────────────────────────────

def wait_for_login(page: Page, *, timeout_s: int = 300) -> None:
    """Block until the human has completed SSO + Duo and Workday is loaded.

    Polls the browser (URL only — no DOM scraping) until a tab is back on the
    Workday tenant and off every SSO/MFA host. Prints a clear prompt telling the
    user to log in. Raises ``TimeoutError`` after ``timeout_s`` seconds.
    """
    print(_LOGIN_PROMPT, flush=True)
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if _active_workday_page(page) is not None:
            print("Workday login detected — continuing.\n", flush=True)
            return
        time.sleep(2.0)
    raise TimeoutError(
        f"Login not completed within {timeout_s}s. Re-run and finish the SSO + "
        "Duo prompt in the opened window. If it keeps failing, fall back to the "
        "manual xlsx upload via the paperclip button in the app."
    )


# ── Export-to-Excel (native download capture — never DOM scraping) ───────────

# Strategy 1: a direct export/Excel button.
_DIRECT_EXPORT_SELECTORS = (
    '[data-automation-id="excelButton"]',
    '[data-automation-id="spreadsheetButton"]',
    '[data-automation-id="exportButton"]',
    '[data-automation-id="viewAllExcelButton"]',
    'button[aria-label*="Excel" i]',
    'button[aria-label*="Export to Excel" i]',
    'button[aria-label*="Export to Spreadsheet" i]',
    'button:has-text("Export to Excel")',
    'button:has-text("Excel")',
)

# Strategy 2: open an Actions / gear menu, then click the Excel item.
_ACTION_OPENERS = (
    '[data-automation-id="actions"]',
    '[data-automation-id="wd-CommandBar-button-exportButton"]',
    'button[aria-label*="Actions" i]',
    'button[aria-label*="More options" i]',
    '[aria-label*="Export" i]',
)
_EXCEL_MENU_ITEMS = (
    '[data-automation-id*="excel" i]',
    '[role="menuitem"]:has-text("Excel")',
    '[role="option"]:has-text("Excel")',
    'li:has-text("Export to Excel")',
    'li:has-text("Excel")',
)

# Strategy 3: enumerate buttons/links and find one that mentions Excel/Export.
# This locates the *export control* — it does not read any academic data.
_DISCOVER_JS = """
() => {
    const out = [];
    for (const n of document.querySelectorAll('button, [role="button"], a')) {
        const text  = (n.textContent || '').trim().toLowerCase();
        const label = (n.getAttribute('aria-label') || '').toLowerCase();
        const aid   = (n.getAttribute('data-automation-id') || '').toLowerCase();
        if (text.includes('excel') || text.includes('export') ||
            label.includes('excel') || label.includes('export') ||
            aid.includes('excel') || aid.includes('export')) {
            out.push({ text, label, aid });
        }
    }
    return out.slice(0, 5);
}
"""


def _download_by_selector(page: Page, selector: str, *, timeout: int = 4_000) -> bytes | None:
    """Click ``selector`` and capture the resulting download as bytes, or None."""
    try:
        page.wait_for_selector(selector, timeout=timeout, state="visible")
        with page.expect_download(timeout=DL_TIMEOUT_MS) as dl_info:
            page.click(selector, timeout=timeout)
        path = dl_info.value.path()
        return Path(path).read_bytes() if path else None
    except Exception:  # noqa: BLE001 — selector absent / no download → try next
        return None


def _download_via_direct(page: Page) -> bytes | None:
    for sel in _DIRECT_EXPORT_SELECTORS:
        data = _download_by_selector(page, sel)
        if data:
            return data
    return None


def _download_via_menu(page: Page) -> bytes | None:
    for opener in _ACTION_OPENERS:
        try:
            page.click(opener, timeout=3_000)
            page.wait_for_timeout(600)
            for item in _EXCEL_MENU_ITEMS:
                data = _download_by_selector(page, item, timeout=3_000)
                if data:
                    return data
            page.keyboard.press("Escape")  # close menu before trying next opener
        except Exception:  # noqa: BLE001
            continue
    return None


def _download_via_js(page: Page) -> bytes | None:
    try:
        candidates = page.evaluate(_DISCOVER_JS)
    except Exception:  # noqa: BLE001
        return None
    for cand in candidates or []:
        if cand.get("aid"):
            sel = f'[data-automation-id="{cand["aid"]}"]'
        elif cand.get("label"):
            sel = f'[aria-label="{cand["label"]}"]'
        elif cand.get("text"):
            sel = f'button:has-text("{cand["text"][:30]}")'
        else:
            continue
        data = _download_by_selector(page, sel)
        if data:
            return data
    return None


def export_to_excel(page: Page, navigate: Callable[[Page], None]) -> bytes:
    """Navigate to the target task page, click *Export to Excel*, return bytes.

    ``navigate(page)`` is a caller-supplied callback that drives ``page`` to the
    specific Workday report (e.g. View My Academic Progress / Find Course
    Sections). We then trigger Workday's native Excel export and capture the
    downloaded file — we never scrape the rendered table.

    Raises ``RuntimeError`` if no export control can be found (a strong signal
    that the Workday layout changed) — callers should abort loudly rather than
    write garbage.
    """
    navigate(page)
    _wait_for_render(page)

    for strategy in (_download_via_direct, _download_via_menu, _download_via_js):
        data = strategy(page)
        if data:
            return data

    hint = ""
    try:
        shot = Path(tempfile.gettempdir()) / "workday_export_debug.png"
        page.screenshot(path=str(shot), full_page=False)
        hint = f" (debug screenshot: {shot})"
    except Exception:  # noqa: BLE001
        pass
    raise RuntimeError(
        "Could not find Workday's 'Export to Excel' control on the report page. "
        "The Workday layout may have changed — aborting instead of guessing." + hint
    )
