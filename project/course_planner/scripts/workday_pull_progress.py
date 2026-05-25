#!/usr/bin/env python3
"""Pull *View My Academic Progress* from Workday and upload or save the export.

Run from ``project/course_planner/`` (see ``scripts/README.md``).

Flow
----
1. Open a **headed** Chromium with a persistent profile (``.workday_profile/``).
2. **You** complete SCU SSO + Duo in that window — this script never sees credentials.
3. Navigate to *View My Academic Progress*, click Workday's native **Export to Excel**.
4. Validate the download in-process; abort loudly if parsing yields no rows.
5. Either POST to the local API (``--user-id``) or write the ``.xlsx`` (``--save``).

Exit codes
----------
* ``0`` — success
* ``1`` — validation failed or API upload failed
* ``2`` — browser launch, login timeout, navigation, or export failed

Cron / automation
-----------------
Everything after login is automatable. The first run (or after session expiry) still
requires a human at the keyboard for SSO + Duo. Keep the API running for POST mode.

Environment
-----------
* ``SCU_WORKDAY_URL`` — override the default Academic Progress task URL.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

# Locate course_planner root (same pattern as scrape_rmp_ratings.py).
_CWD = Path.cwd()
_SCRIPT_ROOT = Path(__file__).resolve().parent.parent


def _find_root() -> Path:
    for candidate in (_CWD, _SCRIPT_ROOT):
        if (candidate / "utils").is_dir() and (candidate / "scripts").is_dir():
            return candidate
    for parent in _CWD.parents:
        cp = parent / "course_planner"
        if (cp / "utils").is_dir():
            return cp
    raise FileNotFoundError(
        "Cannot find course_planner root. Run from project/course_planner/."
    )


_HERE = _find_root()
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from playwright.sync_api import Page, TimeoutError as PWTimeout  # noqa: E402

from scripts._workday_browser import export_to_excel, launch, wait_for_login  # noqa: E402
from utils.academic_progress_helpers import enrich_missing_details  # noqa: E402
from utils.academic_progress_xlsx import parse_academic_progress_xlsx  # noqa: E402

# ── Config ───────────────────────────────────────────────────────────────────

TASK_URL = os.environ.get(
    "SCU_WORKDAY_URL",
    "https://www.myworkday.com/scu/d/task/2998$44123.htmld",
)
DEFAULT_PROFILE_DIR = _HERE / ".workday_profile"
DEFAULT_UPLOAD_URL = "http://localhost:8000/api/upload/transcript"

NAV_TIMEOUT_MS = 60 * 1000
RENDER_WAIT_MS = 4_000

_ACADEMIC_PROGRESS_HEADINGS = (
    "view my academic progress",
    "academic progress",
    "my academic progress",
)
_SEARCH_QUERY = "View My Academic Progress"


class ProgressValidationError(Exception):
    """Parsed Workday export is empty — layout likely changed."""


# ── Navigation (recovered from utils/workday_scraper.py @ c095321^) ───────────


def _wait_for_workday_content(page: Page) -> None:
    try:
        page.wait_for_load_state("domcontentloaded", timeout=30_000)
    except PWTimeout:
        pass
    page.wait_for_timeout(RENDER_WAIT_MS)


def _on_academic_progress_page(page: Page) -> bool:
    try:
        title = (page.title() or "").lower()
        if any(h in title for h in _ACADEMIC_PROGRESS_HEADINGS):
            return True
        heading = page.evaluate(
            "() => (document.querySelector('h1, [role=\"heading\"]') || {}).textContent || ''"
        )
        return any(h in str(heading).lower() for h in _ACADEMIC_PROGRESS_HEADINGS)
    except Exception:  # noqa: BLE001
        return False


def _try_search_for_report(page: Page) -> bool:
    search_box_selectors = [
        '[data-automation-id="globalSearchBox"]',
        '[data-automation-id="searchBox"]',
        '[data-automation-id="GLOBAL_SEARCH_BOX"]',
        'input[aria-label*="Search" i]',
        'input[placeholder*="Search" i]',
    ]
    box = None
    for sel in search_box_selectors:
        try:
            page.wait_for_selector(sel, timeout=4_000, state="visible")
            box = page.locator(sel).first
            box.click()
            break
        except Exception:  # noqa: BLE001
            box = None
            continue
    if box is None:
        return False

    try:
        box.fill(_SEARCH_QUERY)
        page.wait_for_timeout(1_500)
        suggestion_selectors = [
            f'text="{_SEARCH_QUERY}"',
            'text="View My Academic Progress"',
            'a:has-text("View My Academic Progress")',
            '[data-automation-id="searchResults"] a',
        ]
        for sel in suggestion_selectors:
            try:
                page.locator(sel).first.click(timeout=3_000)
                _wait_for_workday_content(page)
                if _on_academic_progress_page(page):
                    return True
            except Exception:  # noqa: BLE001
                continue
        page.keyboard.press("Enter")
        _wait_for_workday_content(page)
        return _on_academic_progress_page(page)
    except Exception:  # noqa: BLE001
        return False


def _ensure_on_task(page: Page, task_url: str = TASK_URL) -> None:
    """Navigate to View My Academic Progress (direct URL, then search fallback)."""
    task_path = task_url.split("/scu/", 1)[-1].split("?")[0].lower()

    _wait_for_workday_content(page)
    if _on_academic_progress_page(page):
        return

    if task_path not in page.url.lower():
        try:
            page.goto(task_url, timeout=NAV_TIMEOUT_MS, wait_until="domcontentloaded")
            _wait_for_workday_content(page)
        except Exception:  # noqa: BLE001
            pass
        if _on_academic_progress_page(page):
            return

    if _try_search_for_report(page):
        return

    actual = ""
    try:
        actual = (page.title() or "").strip()
    except Exception:  # noqa: BLE001
        pass
    raise RuntimeError(
        "Could not reach 'View My Academic Progress' in Workday"
        + (f" — currently on {actual!r}." if actual else ".")
        + "\nThe SCU_WORKDAY_URL task ID may be stale and the search fallback failed. "
        "Workaround: export manually in Workday and upload via the paperclip in the app."
    )


def navigate_to_academic_progress(page: Page) -> None:
    """``navigate`` callback for ``export_to_excel``."""
    _ensure_on_task(page)


# ── Validation & upload ───────────────────────────────────────────────────────


def validate_progress_export(xlsx_bytes: bytes) -> dict[str, Any]:
    """Parse export bytes; raise if both ``detail_rows`` and ``not_satisfied`` are empty."""
    data = parse_academic_progress_xlsx(xlsx_bytes)
    detail_rows = data.get("detail_rows") or []
    not_satisfied = data.get("not_satisfied") or []
    if not detail_rows and not not_satisfied:
        raise ProgressValidationError(
            "Workday export parsed to ZERO rows (detail_rows and not_satisfied both empty).\n"
            "The Academic Progress Excel layout may have changed — NOT writing or uploading "
            "this file. Re-export manually or update the parser."
        )
    return data


def _post_transcript(
    xlsx_bytes: bytes,
    *,
    user_id: str,
    upload_url: str = DEFAULT_UPLOAD_URL,
) -> dict[str, Any]:
    import requests

    files = {
        "file": (
            "academic_progress.xlsx",
            xlsx_bytes,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ),
    }
    data = {"user_id": user_id}
    resp = requests.post(upload_url, files=files, data=data, timeout=120)
    resp.raise_for_status()
    body = resp.json()
    if not isinstance(body, dict):
        raise RuntimeError(f"Unexpected API response type: {type(body)!r}")
    return body


def _print_upload_summary(body: dict[str, Any], parsed: dict[str, Any]) -> None:
    missing = body.get("missing_details")
    if missing is None:
        detail_rows = parsed.get("detail_rows") or []
        not_satisfied = parsed.get("not_satisfied") or []
        missing = enrich_missing_details(not_satisfied, detail_rows)
    parsed_rows = body.get("parsed_rows") or []
    print(f"missing_details: {len(missing)}")
    print(f"parsed_rows: {len(parsed_rows)}")


# ── CLI ───────────────────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Pull View My Academic Progress from Workday (headed browser, human login).",
    )
    p.add_argument(
        "--user-id",
        metavar="ID",
        help="User id for POST /api/upload/transcript (required unless --save).",
    )
    p.add_argument(
        "--save",
        metavar="PATH",
        type=Path,
        help="Write the .xlsx to PATH instead of uploading.",
    )
    p.add_argument(
        "--profile-dir",
        type=Path,
        default=DEFAULT_PROFILE_DIR,
        help=f"Persistent Chromium profile (default: {DEFAULT_PROFILE_DIR}).",
    )
    p.add_argument(
        "--upload-url",
        default=DEFAULT_UPLOAD_URL,
        help=f"Upload endpoint (default: {DEFAULT_UPLOAD_URL}).",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.save:
        do_upload = False
    elif args.user_id:
        do_upload = True
    else:
        _build_parser().error("one of --user-id or --save is required")

    context = None
    try:
        context, page = launch(args.profile_dir)
        wait_for_login(page)
        xlsx_bytes = export_to_excel(page, navigate_to_academic_progress)
    except TimeoutError as exc:
        print(f"ERROR (login): {exc}", file=sys.stderr)
        return 2
    except RuntimeError as exc:
        print(f"ERROR (browser/export): {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 — Playwright / launch failures
        print(f"ERROR (browser): {exc}", file=sys.stderr)
        return 2
    finally:
        if context is not None:
            try:
                context.close()
            except Exception:  # noqa: BLE001
                pass

    try:
        parsed = validate_progress_export(xlsx_bytes)
    except ProgressValidationError as exc:
        print(f"\n{'=' * 60}\nVALIDATION FAILED\n{'=' * 60}", file=sys.stderr)
        print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR (parse): {exc}", file=sys.stderr)
        return 1

    if args.save:
        out = args.save.expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(xlsx_bytes)
        print(f"Saved {len(xlsx_bytes)} bytes → {out}")
        print(
            f"parsed: detail_rows={len(parsed.get('detail_rows') or [])}, "
            f"not_satisfied={len(parsed.get('not_satisfied') or [])}"
        )
        return 0

    try:
        body = _post_transcript(
            xlsx_bytes,
            user_id=args.user_id.strip(),
            upload_url=args.upload_url,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR (upload): {exc}", file=sys.stderr)
        return 1

    _print_upload_summary(body, parsed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
