"""
Playwright-based Workday scraper for SCU Academic Progress.

Flow:
  1. Open Chromium (visible) and navigate directly to the task URL.
     Workday redirects to SCU SSO automatically.
  2. Wait for the student to complete SSO / MFA (up to 5 min).
  3. If redirected to home after SSO, navigate back to the task URL.
  4. Export the report to Excel.
  5. Parse and return missing_details.

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

# Workday tenant root — everything after this up to /d/ is the tenant path
_WORKDAY_BASE = "myworkday.com/scu"

LOGIN_TIMEOUT_MS = 5 * 60 * 1000   # 5 min for SSO / MFA
NAV_TIMEOUT_MS   = 60 * 1000
DL_TIMEOUT_MS    = 90 * 1000


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

def _ensure_on_task(page: Page, task_url: str, cb: Callable[[str], None]) -> None:
    """After login, make sure we're on the Academic Progress task page."""
    task_path = task_url.split("/scu/", 1)[-1].split("?")[0].lower()
    if task_path not in page.url.lower():
        cb("navigating")
        page.goto(task_url, timeout=NAV_TIMEOUT_MS)
        page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT_MS)


# ── Excel export ──────────────────────────────────────────────────────────────

def _export_to_excel(page: Page, download_dir: Path, cb: Callable[[str], None]) -> Path:
    cb("downloading")

    # Workday shows the report as a grid/table. Common export selectors:
    export_selectors = [
        # Workday's built-in "Export to Excel" / "Export to Spreadsheet" buttons
        '[data-automation-id="excelButton"]',
        '[data-automation-id="spreadsheetButton"]',
        '[data-automation-id="exportButton"]',
        '[data-automation-id="viewAllExcelButton"]',
        # Aria-label based
        'button[aria-label*="Excel" i]',
        'button[aria-label*="Export" i]',
        'button[aria-label*="Spreadsheet" i]',
        # Text-based fallbacks
        'button:has-text("Excel")',
        'button:has-text("Export")',
        'button:has-text("Spreadsheet")',
        # Generic download icon
        '[data-automation-id*="download" i]',
    ]

    for sel in export_selectors:
        try:
            page.wait_for_selector(sel, timeout=6000)
            with page.expect_download(timeout=DL_TIMEOUT_MS) as dl_info:
                page.click(sel, timeout=6000)
            dl = dl_info.value
            dest = download_dir / "academic_progress.xlsx"
            dl.save_as(str(dest))
            return dest
        except (PWTimeout, Exception):
            continue

    # Try the Actions / gear menu as a fallback
    action_selectors = [
        '[data-automation-id="actions"]',
        '[aria-label*="Actions" i]',
        '[aria-label*="More" i]',
        'button:has-text("Actions")',
    ]
    for act_sel in action_selectors:
        try:
            page.click(act_sel, timeout=5000)
            page.wait_for_timeout(800)
            with page.expect_download(timeout=DL_TIMEOUT_MS) as dl_info:
                page.click(
                    '[data-automation-id*="excel" i], '
                    'text="Export to Excel", text="Export to Spreadsheet", '
                    'text="Excel"',
                    timeout=6000,
                )
            dl = dl_info.value
            dest = download_dir / "academic_progress.xlsx"
            dl.save_as(str(dest))
            return dest
        except (PWTimeout, Exception):
            continue

    raise RuntimeError(
        "Could not find an Excel export button on the Academic Progress page.\n"
        "The Workday UI may have changed — please export the file manually "
        "(look for an Excel/Export icon on the report page) and upload it."
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
                page.goto(task_url, timeout=30000)

                # Wait for student to complete SSO / MFA
                _wait_for_login(page, cb)
                cb("logged_in")

                # If SSO redirected to Workday home, navigate back to the task
                _ensure_on_task(page, task_url, cb)
                cb("report_open")

                # Export to Excel
                xlsx_path = _export_to_excel(page, download_dir, cb)

                cb("parsing")
                raw_bytes = xlsx_path.read_bytes()
                parsed = parse_academic_progress_xlsx(raw_bytes)
                return {
                    "missing_details": parsed.get("not_satisfied") or [],
                    "parsed_rows": parsed.get("detail_rows") or [],
                }

            finally:
                try:
                    browser.close()
                except Exception:
                    pass
