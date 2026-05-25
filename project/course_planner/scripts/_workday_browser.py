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
    page = wait_for_login(page)                # blocks; returns the Workday tab
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

__all__ = [
    "launch",
    "wait_for_login",
    "export_to_excel",
    "export_controls_visible",
    "export_document_modal_visible",
]

# ── Config ──────────────────────────────────────────────────────────────────

# Landing URL. Hitting the SCU tenant while unauthenticated triggers the
# Workday → SSO redirect, which is exactly the login flow we want the human to
# complete in the visible window.
# SCU redirects between www and bare host; bare host matches the post-login dashboard.
WORKDAY_HOME = "https://myworkday.com/scu/d/home.htmld"
WORKDAY_HOME_ALT = "https://www.myworkday.com/scu/d/home.htmld"

# SCU tenant markers (www and wd5 hosts).
WORKDAY_BASE = "myworkday.com/scu"

# External SSO/MFA hosts only — do NOT use bare "auth" / "duo" on myworkday.com
# URLs or we never detect login (false positives on gateway paths).
_EXTERNAL_SSO_MARKERS = (
    "microsoftonline.com",
    "duosecurity.com",
    "shibboleth",
    "login.scu.edu",
    "sso.scu.edu",
    "adfs",
    "okta.com",
    "/saml",
    "/oauth",
)

NAV_TIMEOUT_MS = 60 * 1000
DL_TIMEOUT_MS = 90 * 1000
RENDER_WAIT_MS = 4_000  # pause after export navigation for the SPA to paint

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

def _url_lower(page: Page) -> str:
    try:
        return (page.url or "").lower()
    except Exception:  # noqa: BLE001
        return ""


def _is_myworkday_host(url: str) -> bool:
    u = url.lower()
    return "myworkday.com" in u or "wd5.myworkday.com" in u


def _on_workday_oidc_authorize(url: str) -> bool:
    """Mid-flight OIDC redirect — not logged in yet (do not treat as the home app)."""
    u = url.lower()
    return "oidc/op/authorize" in u or "oidc/authorize" in u


def _on_workday_login_path(url: str) -> bool:
    """True when still on a Workday-branded login page (not OIDC handoff, not home)."""
    u = url.lower()
    if _on_workday_oidc_authorize(u):
        return False
    if "authgwy" in u and "login" in u:
        return True
    return any(frag in u for frag in ("/login.htmld", "/signin.htmld", "/login?", "/signin?"))


def _on_external_sso(url: str) -> bool:
    u = url.lower()
    if _is_myworkday_host(u):
        return False
    if any(m in u for m in _EXTERNAL_SSO_MARKERS):
        return True
    if "scu.edu" in u and any(x in u for x in ("login", "sso", "shibboleth", "saml")):
        return True
    return any(x in u for x in ("login.", "/login", "signin", "duosecurity", "microsoftonline"))


def _on_sso_page(page: Page) -> bool:
    u = _url_lower(page)
    if _on_external_sso(u):
        return True
    return _is_myworkday_host(u) and _on_workday_login_path(u)


def _is_workday_home_url(url: str) -> bool:
    u = url.lower()
    return "home.htmld" in u and ("/scu/" in u or "myworkday.com/scu" in u)


def _page_title_looks_like_home(page: Page) -> bool:
    try:
        t = (page.title() or "").lower()
        return "workday" in t and "home" in t
    except Exception:  # noqa: BLE001
        return False


def _on_workday(page: Page) -> bool:
    u = _url_lower(page)
    if not _is_myworkday_host(u):
        return False
    if _on_workday_oidc_authorize(u):
        return False
    if _on_sso_page(page):
        return False
    # Logged-in: SCU tenant app (home, tasks, inbox, etc.)
    if _is_workday_home_url(u):
        return True
    if "myworkday.com/scu" in u or "wd5.myworkday.com/scu" in u:
        return True
    if "/authgwy/scu" in u and ("/d/" in u or "home.htmld" in u):
        return True
    if "/d/" in u and ".htmld" in u:
        return True
    if _page_title_looks_like_home(page):
        return True
    return False


def _print_open_tab_urls(page: Page) -> None:
    try:
        urls = [p.url for p in page.context.pages]
    except Exception:  # noqa: BLE001
        urls = [getattr(page, "url", "")]
    print("Still waiting for login. Open browser tabs:", flush=True)
    for i, url in enumerate(urls, 1):
        print(f"  [{i}] {url}", flush=True)
    print(
        "Complete SSO + Duo in the Chromium window that THIS app opened — "
        "not your everyday Chrome/Safari. The active tab must reach "
        "myworkday.com/scu/d/home.htmld (not …/oidc/op/authorize).",
        flush=True,
    )


def _nudge_toward_home(page: Page) -> None:
    """If SSO finished but the tab is stuck on authorize, reload the SCU home URL."""
    for target in (WORKDAY_HOME, WORKDAY_HOME_ALT):
        try:
            page.goto(target, wait_until="domcontentloaded", timeout=25_000)
            page.wait_for_timeout(1_500)
        except Exception:  # noqa: BLE001
            continue


def _active_workday_page(initial: Page) -> Page | None:
    """Return whichever tab in the context is on Workday (past SSO), or None.

    SSO can land the post-login session in a new tab, so we scan every page in
    the context rather than only the one we opened. Prefer the home dashboard.
    """
    pages: list[Page] = []
    try:
        pages = list(initial.context.pages)
    except Exception:  # noqa: BLE001
        pages = [initial]
    home_tab: Page | None = None
    any_tab: Page | None = None
    for p in pages:
        u = _url_lower(p)
        if _on_workday_oidc_authorize(u) or _on_external_sso(u):
            continue
        if _on_workday(p):
            any_tab = any_tab or p
            if _is_workday_home_url(u) or _page_title_looks_like_home(p):
                home_tab = p
    if home_tab is not None:
        return home_tab
    if any_tab is not None:
        return any_tab
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

def wait_for_login(
    page: Page,
    *,
    timeout_s: int = 300,
    poll_hint_s: int = 45,
    progress_cb: Callable[[str], None] | None = None,
) -> Page:
    """Block until the human has completed SSO + Duo and Workday is loaded.

    Polls the browser (URL only — no DOM scraping) until a tab is back on the
    Workday tenant and off every SSO/MFA host. Returns that tab's ``Page``
    (SSO often opens Workday in a *new* tab — callers must use the return value).
    Raises ``TimeoutError`` after ``timeout_s`` seconds.
    """
    print(_LOGIN_PROMPT, flush=True)
    if progress_cb is not None:
        progress_cb("browser_open")
    deadline = time.monotonic() + timeout_s
    next_hint = time.monotonic() + poll_hint_s
    last_nudge = 0.0
    while time.monotonic() < deadline:
        active = _active_workday_page(page)
        if active is not None:
            try:
                active.bring_to_front()
            except Exception:  # noqa: BLE001
                pass
            print(f"Workday login detected ({active.url}) — continuing.\n", flush=True)
            if progress_cb is not None:
                progress_cb("logged_in")
            return active
        now = time.monotonic()
        if now - last_nudge >= 25.0:
            last_nudge = now
            print("Nudging browser toward SCU Workday home…", flush=True)
            try:
                for p in page.context.pages:
                    _nudge_toward_home(p)
            except Exception:  # noqa: BLE001
                _nudge_toward_home(page)
        if now >= next_hint:
            _print_open_tab_urls(page)
            next_hint = now + poll_hint_s
        time.sleep(2.0)
    _print_open_tab_urls(page)
    raise TimeoutError(
        f"Login not completed within {timeout_s}s.\n"
        "Checklist:\n"
        "  • Log in inside the Chromium window this script opened (not another browser).\n"
        "  • Finish Duo on your phone when prompted.\n"
        "  • Wait until the URL shows myworkday.com/scu/... (home or a report).\n"
        "  • If you are already on Workday home, re-run with:\n"
        "      WORKDAY_LOGIN_MANUAL=1 python scripts/workday_pull_progress.py --user-id …\n"
        "    then press Enter in this terminal when the home page is visible.\n"
        "  • Or upload the xlsx manually via the paperclip in the app."
    )


# ── Export-to-Excel (native download capture — never DOM scraping) ───────────

# Strategy 1: a direct export/Excel button (incl. SCU report toolbar icons).
_DIRECT_EXPORT_SELECTORS = (
    '[data-automation-id="excelButton"]',
    '[data-automation-id="spreadsheetButton"]',
    '[data-automation-id="exportButton"]',
    '[data-automation-id="viewAllExcelButton"]',
    '[data-automation-id*="excel" i]',
    '[data-automation-id*="xlsx" i]',
    '[aria-label*="Microsoft Excel" i]',
    '[aria-label*="Export to Excel" i]',
    '[aria-label*="Export to Spreadsheet" i]',
    '[aria-label*="Excel" i]',
    '[title*="Excel" i]',
    '[title*="Spreadsheet" i]',
    'button[aria-label*="Excel" i]',
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


def export_document_modal_visible(page: Page) -> bool:
    """Public alias — Export Document dialog with Download (SCU two-step export)."""
    return _export_document_modal_visible(page)


def _export_document_modal_visible(page: Page) -> bool:
    """SCU opens an *Export Document* dialog with a blue *Download* button."""
    try:
        if page.get_by_role("button", name="Download").first.is_visible(timeout=1_500):
            return page.get_by_text("Export Document", exact=False).first.is_visible(timeout=500)
    except Exception:  # noqa: BLE001
        pass
    try:
        return page.get_by_text("Export Document", exact=False).first.is_visible(timeout=1_000)
    except Exception:  # noqa: BLE001
        return False


def _click_export_document_download(page: Page) -> bytes | None:
    """Click *Download* on the Export Document modal and return file bytes."""
    print("Clicking Download on Export Document dialog…", flush=True)
    for target in (
        page.get_by_role("button", name="Download").first,
        page.locator('button:has-text("Download")').first,
        page.locator('[data-automation-id="downloadButton"]').first,
    ):
        try:
            with page.expect_download(timeout=DL_TIMEOUT_MS) as dl_info:
                target.click(timeout=5_000)
            path = dl_info.value.path()
            if path:
                data = Path(path).read_bytes()
                print(f"Downloaded {len(data)} bytes from Export Document dialog.", flush=True)
                return data
        except Exception:  # noqa: BLE001
            continue
    return None


def _finish_export_download(page: Page) -> bytes | None:
    """After clicking the Excel icon: SCU uses a two-step Export Document → Download."""
    page.wait_for_timeout(1_000)
    if _export_document_modal_visible(page):
        return _click_export_document_download(page)
    try:
        download = page.wait_for_event("download", timeout=10_000)
        path = download.path()
        if path:
            data = Path(path).read_bytes()
            print(f"Captured download ({len(data)} bytes).", flush=True)
            return data
    except Exception:  # noqa: BLE001
        pass
    return None


def _download_by_selector(page: Page, selector: str, *, timeout: int = 4_000) -> bytes | None:
    """Click ``selector``, then complete Export Document → Download if shown."""
    try:
        page.wait_for_selector(selector, timeout=timeout, state="visible")
        page.click(selector, timeout=timeout)
        return _finish_export_download(page)
    except Exception:  # noqa: BLE001 — selector absent / no download → try next
        return None


def _download_via_export_document_modal(page: Page) -> bytes | None:
    """Modal already open (e.g. user clicked Excel manually)."""
    if _export_document_modal_visible(page):
        return _click_export_document_download(page)
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


_CLICK_EXCEL_TOOLBAR_JS = """
() => {
  for (const n of document.querySelectorAll(
    'button, [role="button"], a, [data-automation-id]'
  )) {
    const label = (n.getAttribute('aria-label') || '').toLowerCase();
    const aid = (n.getAttribute('data-automation-id') || '').toLowerCase();
    const title = (n.getAttribute('title') || '').toLowerCase();
    if (
      label.includes('excel') || label.includes('spreadsheet') ||
      aid.includes('excel') || aid.includes('xlsx') ||
      title.includes('excel') || title.includes('spreadsheet')
    ) {
      n.click();
      return true;
    }
  }
  return false;
}
"""


def _download_via_excel_toolbar_js(page: Page) -> bytes | None:
    try:
        clicked = page.evaluate(_CLICK_EXCEL_TOOLBAR_JS)
    except Exception:  # noqa: BLE001
        return None
    if clicked:
        return _finish_export_download(page)
    return None


def export_controls_visible(page: Page) -> bool:
    """True when the report toolbar shows Excel/export or the Export Document modal is open."""
    if _export_document_modal_visible(page):
        return True
    for sel in _DIRECT_EXPORT_SELECTORS:
        try:
            if page.locator(sel).first.is_visible(timeout=600):
                return True
        except Exception:  # noqa: BLE001
            continue
    for opener in _ACTION_OPENERS[:3]:
        try:
            if page.locator(opener).first.is_visible(timeout=400):
                return True
        except Exception:  # noqa: BLE001
            continue
    return False


def export_to_excel(
    page: Page,
    navigate: Callable[[Page], None],
    *,
    on_poll: Callable[[], None] | None = None,
    poll_timeout_s: int = 120,
) -> bytes:
    """Navigate to the target task page, click *Export to Excel*, return bytes.

    ``navigate(page)`` is a caller-supplied callback that drives ``page`` to the
    specific Workday report (e.g. View My Academic Progress / Find Course
    Sections). We then trigger Workday's native Excel export and capture the
    downloaded file — we never scrape the rendered table.

    SCU often uses a two-step flow: Excel icon → *Export Document* modal →
    *Download* (file bytes are read in memory, not left in ~/Downloads).

    Raises ``RuntimeError`` if no export control can be found (a strong signal
    that the Workday layout changed) — callers should abort loudly rather than
    write garbage.
    """
    navigate(page)
    _wait_for_render(page)

    strategies = (
        _download_via_export_document_modal,
        _download_via_direct,
        _download_via_excel_toolbar_js,
        _download_via_menu,
        _download_via_js,
        _download_via_export_document_modal,
    )
    deadline = time.monotonic() + poll_timeout_s
    last_hint_print = 0.0
    while time.monotonic() < deadline:
        for strategy in strategies:
            data = strategy(page)
            if data:
                return data
        if on_poll is not None:
            on_poll()
        now = time.monotonic()
        if now - last_hint_print >= 12.0:
            print(
                "Waiting for Excel export — click the spreadsheet icon on the report "
                "toolbar, then Download in the Export Document dialog if it appears.",
                flush=True,
            )
            last_hint_print = now
        page.wait_for_timeout(2_000)

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
