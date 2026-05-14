"""
Playwright-based Workday scraper for SCU Academic Progress.

Flow:
  1. Open Chromium (visible) and navigate directly to the task URL.
     Workday redirects to SCU SSO automatically.
  2. Wait for the student to complete SSO / MFA (up to 5 min).
  3. If redirected to home after SSO, navigate back to the task URL.
  4. Wait for the report content to render (not networkidle — Workday SPA never settles).
  5. Export the report to Excel.
  6. Parse and return missing_details.

Configuration:
  SCU_WORKDAY_URL=https://www.myworkday.com/scu/d/task/2998$44123.htmld
  (already set in .env — this is the direct "View My Academic Progress" URL)
"""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path
from typing import Callable

from playwright.sync_api import (
    Page,
    TimeoutError as PWTimeout,
    sync_playwright,
)

from utils.academic_progress_xlsx import parse_academic_progress_xlsx

# ── Config ───────────────────────────────────────────────────────────────────

TASK_URL = os.environ.get(
    "SCU_WORKDAY_URL",
    "https://www.myworkday.com/scu/d/task/2998$44123.htmld",
)

_WORKDAY_BASE = "myworkday.com/scu"

LOGIN_TIMEOUT_MS  = 5 * 60 * 1000   # 5 min for SSO / MFA
NAV_TIMEOUT_MS    = 60 * 1000
DL_TIMEOUT_MS     = 90 * 1000
RENDER_WAIT_MS    = 4_000           # Extra time after navigation for JS rendering


# ── Login detection ───────────────────────────────────────────────────────────

_SSO_KEYWORDS = ("login", "sso", "saml", "oauth", "auth", "signin",
                 "adfs", "okta", "microsoftonline", "shibboleth")


def _on_sso_page(page: Page) -> bool:
    url = page.url.lower()
    return any(kw in url for kw in _SSO_KEYWORDS)


def _on_workday(page: Page) -> bool:
    return _WORKDAY_BASE in page.url.lower() and not _on_sso_page(page)


def _wait_for_login(page: Page, cb: Callable[[str], None]) -> None:
    """Block until the browser is on a Workday page (not SSO)."""
    cb("browser_open")
    deadline = time.monotonic() + LOGIN_TIMEOUT_MS / 1000
    while time.monotonic() < deadline:
        if _on_workday(page):
            return
        time.sleep(1.5)
    raise TimeoutError(
        "Login timed out after 5 minutes — please try again and complete SSO promptly."
    )


# ── Report navigation ─────────────────────────────────────────────────────────

def _wait_for_workday_content(page: Page) -> None:
    """Wait for Workday page content to render.

    Workday is a heavy SPA — wait_for_load_state('networkidle') hangs
    because the app constantly polls APIs. Instead we wait for
    domcontentloaded + a brief fixed pause, then check for any Workday
    content element before proceeding.
    """
    try:
        page.wait_for_load_state("domcontentloaded", timeout=30_000)
    except PWTimeout:
        pass  # proceed anyway — DOM may already be ready
    page.wait_for_timeout(RENDER_WAIT_MS)


def _ensure_on_task(page: Page, task_url: str, cb: Callable[[str], None]) -> None:
    """After login, make sure we're on the Academic Progress task page."""
    task_path = task_url.split("/scu/", 1)[-1].split("?")[0].lower()
    if task_path not in page.url.lower():
        cb("navigating")
        page.goto(task_url, timeout=NAV_TIMEOUT_MS, wait_until="domcontentloaded")
    cb("searching")
    _wait_for_workday_content(page)


# ── Excel export ──────────────────────────────────────────────────────────────

def _try_click_download(page: Page, sel: str, dest: Path, timeout: int = 4_000) -> bool:
    """Try clicking a selector and waiting for a download. Returns True on success."""
    try:
        page.wait_for_selector(sel, timeout=timeout, state="visible")
        with page.expect_download(timeout=DL_TIMEOUT_MS) as dl_info:
            page.click(sel, timeout=timeout)
        dl = dl_info.value
        dl.save_as(str(dest))
        return True
    except Exception:  # noqa: BLE001
        return False


def _export_to_excel(page: Page, download_dir: Path, cb: Callable[[str], None]) -> Path:
    cb("downloading")
    dest = download_dir / "academic_progress.xlsx"

    # ── Strategy 1: direct export/Excel buttons ──────────────────────────────
    direct_selectors = [
        '[data-automation-id="excelButton"]',
        '[data-automation-id="spreadsheetButton"]',
        '[data-automation-id="exportButton"]',
        '[data-automation-id="viewAllExcelButton"]',
        'button[aria-label*="Excel" i]',
        'button[aria-label*="Export to Excel" i]',
        'button[aria-label*="Export to Spreadsheet" i]',
        'button:has-text("Export to Excel")',
        'button:has-text("Excel")',
    ]
    for sel in direct_selectors:
        if _try_click_download(page, sel, dest):
            return dest

    # ── Strategy 2: open an Actions / gear menu, then click the Excel item ───
    action_openers = [
        '[data-automation-id="actions"]',
        '[data-automation-id="wd-CommandBar-button-exportButton"]',
        'button[aria-label*="Actions" i]',
        'button[aria-label*="More options" i]',
        '[aria-label*="Export" i]',
    ]
    excel_in_menu = [
        '[data-automation-id*="excel" i]',
        '[role="menuitem"]:has-text("Excel")',
        '[role="option"]:has-text("Excel")',
        'li:has-text("Export to Excel")',
        'li:has-text("Excel")',
    ]
    for opener in action_openers:
        try:
            page.click(opener, timeout=3_000)
            page.wait_for_timeout(600)
            for menu_sel in excel_in_menu:
                if _try_click_download(page, menu_sel, dest, timeout=3_000):
                    return dest
            # Close the menu if we didn't find anything useful
            page.keyboard.press("Escape")
        except Exception:  # noqa: BLE001
            continue

    # ── Strategy 3: JavaScript discovery ────────────────────────────────────
    # Find any button/link that mentions Excel or Export in its text / aria / automation-id.
    try:
        candidates: list[dict] = page.evaluate("""
            () => {
                const results = [];
                const nodes = document.querySelectorAll('button, [role="button"], a');
                for (const n of nodes) {
                    const text = (n.textContent || '').trim().toLowerCase();
                    const label = (n.getAttribute('aria-label') || '').toLowerCase();
                    const aid   = (n.getAttribute('data-automation-id') || '').toLowerCase();
                    if (
                        text.includes('excel') || text.includes('export') ||
                        label.includes('excel') || label.includes('export') ||
                        aid.includes('excel')  || aid.includes('export')
                    ) {
                        results.push({ text, label, aid });
                    }
                }
                return results.slice(0, 5);
            }
        """)
        for cand in candidates:
            # Build a selector for this candidate
            if cand.get("aid"):
                sel = f'[data-automation-id="{cand["aid"]}"]'
            elif cand.get("label"):
                sel = f'[aria-label="{cand["label"]}"]'
            else:
                sel = f'button:has-text("{cand["text"][:30]}")'
            if _try_click_download(page, sel, dest):
                return dest
    except Exception:  # noqa: BLE001
        pass

    # ── Fallback: save a screenshot so the user can diagnose ─────────────────
    try:
        screenshot_path = Path(tempfile.gettempdir()) / "workday_debug.png"
        page.screenshot(path=str(screenshot_path), full_page=False)
    except Exception:  # noqa: BLE001
        screenshot_path = None

    hint = (
        f" (debug screenshot saved to {screenshot_path})" if screenshot_path else ""
    )
    raise RuntimeError(
        "Could not find the Excel export button on the Academic Progress page.\n"
        "The Workday UI may look different — try exporting manually:\n"
        "  1. On the report page, look for an Excel icon or an 'Actions' ⚙ menu\n"
        "  2. Click 'Export to Excel' and download the file\n"
        "  3. Upload it with the 📎 button in the chat panel." + hint
    )


# ── Main entry point ──────────────────────────────────────────────────────────

def scrape_workday_sync(
    workday_url: str | None = None,
    progress_cb: Callable[[str], None] | None = None,
) -> dict:
    """
    Run the full Workday scrape in the calling thread (call from a background thread).

    Returns {"missing_details": [...], "parsed_rows": [...]}
    Raises RuntimeError / TimeoutError on failure.
    """
    cb = progress_cb or (lambda _: None)
    task_url = (workday_url or TASK_URL).strip()

    with tempfile.TemporaryDirectory() as tmpdir:
        download_dir = Path(tmpdir)

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=False,
                args=["--start-maximized"],
            )
            context = browser.new_context(
                accept_downloads=True,
                viewport={"width": 1440, "height": 900},
            )
            page = context.new_page()

            try:
                # Navigate directly to the task — Workday auto-redirects to SSO
                cb("navigating")
                page.goto(task_url, timeout=30_000, wait_until="domcontentloaded")

                # Wait for student to complete SSO / MFA
                _wait_for_login(page, cb)
                cb("logged_in")

                # Navigate to task page if SSO landed elsewhere
                _ensure_on_task(page, task_url, cb)
                cb("report_open")

                # Export to Excel
                xlsx_path = _export_to_excel(page, download_dir, cb)

                cb("parsing")
                raw_bytes = xlsx_path.read_bytes()
                parsed = parse_academic_progress_xlsx(raw_bytes)
                return {
                    "missing_details": parsed.get("not_satisfied") or [],
                    "parsed_rows":     parsed.get("detail_rows") or [],
                }

            finally:
                try:
                    browser.close()
                except Exception:
                    pass
