"""
Playwright-based Workday scraper for SCU Academic Progress.

Flow:
  1. Open Chromium (visible) at the configured Workday URL.
  2. Wait up to 5 min for the student to complete SSO / MFA.
  3. Use Workday's global search to open "View My Academic Progress".
  4. Export the report to Excel.
  5. Return the raw bytes and the parsed missing_details.

Configuration:
  Set SCU_WORKDAY_URL in .env, e.g.:
    SCU_WORKDAY_URL=https://wd5.myworkday.com/scu/d/home.htmld

Usage (in a background thread — do NOT await):
  result = scrape_workday_sync(progress_cb=lambda msg: print(msg))
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

DEFAULT_WORKDAY_URL = os.environ.get(
    "SCU_WORKDAY_URL",
    "https://wd5.myworkday.com/scu/d/home.htmld",
)

LOGIN_TIMEOUT_MS = 5 * 60 * 1000   # 5 min for SSO / MFA
NAV_TIMEOUT_MS   = 60 * 1000       # 60 s for page actions after login
DL_TIMEOUT_MS    = 90 * 1000       # 90 s download


# ── Helpers ──────────────────────────────────────────────────────────────────

def _is_logged_in(page: Page, workday_base: str) -> bool:
    url = page.url.lower()
    base = workday_base.lower().split("/d/")[0]   # e.g. "https://wd5.myworkday.com/scu"
    if base not in url:
        return False
    # SSO/login pages contain these keywords
    for kw in ("login", "sso", "saml", "oauth", "auth", "signin", "adfs", "okta", "microsoftonline"):
        if kw in url:
            return False
    # Check for a Workday home element
    try:
        page.wait_for_selector('[data-automation-id="workdayLogo"], [data-automation-id="home"], '
                               '[aria-label="Home"], [data-automation-id="globalNav"]',
                               timeout=2000)
        return True
    except PWTimeout:
        return False


def _wait_for_login(page: Page, workday_base: str, cb: Callable[[str], None]) -> None:
    cb("browser_open")
    deadline = time.monotonic() + LOGIN_TIMEOUT_MS / 1000
    while time.monotonic() < deadline:
        if _is_logged_in(page, workday_base):
            return
        time.sleep(2)
    raise TimeoutError("Login timed out after 5 minutes. Please try again.")


def _open_academic_progress(page: Page, cb: Callable[[str], None]) -> None:
    cb("searching")

    # Strategy 1: Workday global search (most reliable across tenants)
    search_selectors = [
        '[data-automation-id="searchInputBox"]',
        '[data-automation-id="searchInput"]',
        '[aria-label="Search"]',
        'input[type="search"]',
        '[placeholder*="Search"]',
    ]
    search_input = None
    for sel in search_selectors:
        try:
            search_input = page.wait_for_selector(sel, timeout=10000)
            if search_input:
                break
        except PWTimeout:
            continue

    if search_input:
        search_input.click()
        search_input.fill("View My Academic Progress")
        page.keyboard.press("Enter")
        page.wait_for_timeout(3000)

        # Click the search result
        result_selectors = [
            'text="View My Academic Progress"',
            '[data-automation-id*="searchResult"] >> text=Academic Progress',
        ]
        for sel in result_selectors:
            try:
                page.click(sel, timeout=10000)
                page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT_MS)
                return
            except (PWTimeout, Exception):
                continue

    # Strategy 2: Navigate via menu
    # Look for "Academics" in the navigation, then "View My Academic Progress"
    try:
        page.click('[data-automation-id*="academics"], text="Academics"', timeout=8000)
        page.click('text="View My Academic Progress"', timeout=8000)
        page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT_MS)
        return
    except (PWTimeout, Exception):
        pass

    raise RuntimeError(
        "Could not find 'View My Academic Progress' in Workday. "
        "Make sure you are logged in and the report is available in your account."
    )


def _export_to_excel(page: Page, download_dir: Path, cb: Callable[[str], None]) -> Path:
    cb("downloading")

    export_selectors = [
        # Common Workday export/download buttons
        '[data-automation-id="excelButton"]',
        '[data-automation-id="downloadButton"]',
        '[aria-label*="Excel"]',
        '[aria-label*="Export"]',
        '[aria-label*="Download"]',
        'button:has-text("Excel")',
        'button:has-text("Export")',
        '[title*="Excel"]',
    ]

    for sel in export_selectors:
        try:
            page.wait_for_selector(sel, timeout=8000)
            with page.expect_download(timeout=DL_TIMEOUT_MS) as dl_info:
                page.click(sel)
            dl = dl_info.value
            dest = download_dir / "academic_progress.xlsx"
            dl.save_as(str(dest))
            return dest
        except (PWTimeout, Exception):
            continue

    # Fallback: try the Actions menu
    try:
        page.click('[data-automation-id="actions"], button:has-text("Actions")', timeout=8000)
        page.wait_for_timeout(1000)
        with page.expect_download(timeout=DL_TIMEOUT_MS) as dl_info:
            page.click('[data-automation-id*="excel"], text="Export to Excel", text="Excel"', timeout=8000)
        dl = dl_info.value
        dest = download_dir / "academic_progress.xlsx"
        dl.save_as(str(dest))
        return dest
    except (PWTimeout, Exception):
        pass

    raise RuntimeError(
        "Could not find the Excel export button on the Academic Progress report page. "
        "The Workday UI may have changed — please export the file manually and upload it."
    )


# ── Main entry point ─────────────────────────────────────────────────────────

def scrape_workday_sync(
    workday_url: str | None = None,
    progress_cb: Callable[[str], None] | None = None,
) -> dict:
    """
    Run the full Workday scrape in the calling thread (use in a background thread).

    Returns:
        {"missing_details": [...], "raw_bytes": bytes}
    Raises:
        RuntimeError / TimeoutError on failure.
    """
    cb = progress_cb or (lambda _: None)
    base_url = (workday_url or DEFAULT_WORKDAY_URL).rstrip("/")

    with tempfile.TemporaryDirectory() as tmpdir:
        download_dir = Path(tmpdir)

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=False,
                args=["--start-maximized"],
            )
            context = browser.new_context(
                accept_downloads=True,
                viewport={"width": 1400, "height": 900},
            )
            page = context.new_page()

            try:
                cb("navigating")
                page.goto(base_url, timeout=30000)

                _wait_for_login(page, base_url, cb)
                cb("logged_in")

                _open_academic_progress(page, cb)
                cb("report_open")

                xlsx_path = _export_to_excel(page, download_dir, cb)
                cb("parsing")

                raw_bytes = xlsx_path.read_bytes()
                parsed = parse_academic_progress_xlsx(raw_bytes)
                # Mirror the upload endpoint's response shape
                return {
                    "missing_details": parsed.get("not_satisfied") or [],
                    "parsed_rows": parsed.get("detail_rows") or [],
                }

            finally:
                try:
                    browser.close()
                except Exception:
                    pass
