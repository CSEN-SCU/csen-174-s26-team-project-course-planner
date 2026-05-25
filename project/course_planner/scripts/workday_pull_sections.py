#!/usr/bin/env python3
"""Admin CLI: refresh the shared next-term *Find Course Sections* catalog.

Opens a **headed** Chromium window; a human completes SCU SSO + Duo. The script
then navigates to Find Course Sections, applies term/level filters, exports to
Excel, validates the download, and atomically overwrites
``SCU_Find_Course_Sections.xlsx``.

Usage (from ``project/course_planner/``)::

    python scripts/workday_pull_sections.py
    python scripts/workday_pull_sections.py --term "Fall 2026" --level Undergraduate

Environment (optional)::

    SCU_WORKDAY_SECTIONS_URL  direct Workday task URL (skips global search)
    SCU_WORKDAY_TERM          default --term when flag omitted
    SCU_WORKDAY_LEVEL         default --level when flag omitted

After a successful run, restart the API or call ``POST /api/courses/refresh``
so ``lru_cache`` schedule indexes pick up the new xlsx (see scripts/README.md).
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from playwright.sync_api import Page

# ── course_planner root on sys.path (same pattern as scrape_rmp_ratings.py) ───

_CWD = Path.cwd()
_SCRIPT_ROOT = Path(__file__).resolve().parent.parent


def find_course_planner_root() -> Path:
    """Return the course_planner/ directory (may not yet contain the xlsx)."""
    marker = "SCU_Find_Course_Sections.xlsx"
    for candidate in (_CWD, _SCRIPT_ROOT):
        if candidate.name == "course_planner" or (candidate / marker).is_file():
            return candidate if candidate.name == "course_planner" else candidate
        cp = candidate / "course_planner"
        if cp.is_dir():
            return cp
    for parent in _CWD.parents:
        cp = parent / "course_planner"
        if cp.is_dir() and (cp / "scripts" / "workday_pull_sections.py").is_file():
            return cp
    if _SCRIPT_ROOT.is_dir():
        return _SCRIPT_ROOT
    raise FileNotFoundError(
        "Cannot locate project/course_planner/. "
        "Run this script from project/course_planner/."
    )


_HERE = find_course_planner_root()
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from scripts import _workday_browser as wb  # noqa: E402
from utils.scu_course_schedule_xlsx import list_offered_courses  # noqa: E402

# ── Paths & exit codes (cron-friendly) ───────────────────────────────────────

PROFILE_DIR = _HERE / ".workday_profile"
DEST_XLSX = _HERE / "SCU_Find_Course_Sections.xlsx"

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_LOGIN = 2
EXIT_NAVIGATION = 3
EXIT_EXPORT = 4
EXIT_VALIDATION = 5
EXIT_WRITE = 6

_SECTIONS_URL_ENV = "SCU_WORKDAY_SECTIONS_URL"
_TERM_ENV = "SCU_WORKDAY_TERM"
_LEVEL_ENV = "SCU_WORKDAY_LEVEL"

_SEARCH_QUERY = "Find Course Sections"
_SECTIONS_HEADINGS = (
    "find course sections",
    "course sections",
)

# Global search box — Workday has renamed these across UI refreshes (fragile).
_SEARCH_BOX_SELECTORS = (
    '[data-automation-id="globalSearchBox"]',
    '[data-automation-id="searchBox"]',
    '[data-automation-id="GLOBAL_SEARCH_BOX"]',
    'input[aria-label*="Search" i]',
    'input[placeholder*="Search" i]',
)

_SEARCH_SUGGESTION_SELECTORS = (
    f'text="{_SEARCH_QUERY}"',
    'text="Find Course Sections"',
    'a:has-text("Find Course Sections")',
    '[data-automation-id="searchResults"] a',
)

# Term / level filters — layout-specific; see navigate_find_course_sections().
_TERM_FILTER_LABELS = (
    "academic period",
    "academic periods",
    "term",
    "period",
    "quarter",
)
_LEVEL_FILTER_LABELS = (
    "academic level",
    "level",
    "student level",
)
_SEARCH_RUN_SELECTORS = (
    '[data-automation-id="searchButton"]',
    '[data-automation-id="submitButton"]',
    'button:has-text("Search")',
    'button:has-text("Go")',
    'button:has-text("Find")',
)


class SectionsValidationError(RuntimeError):
    """Downloaded xlsx parsed to zero offered courses."""


# ── Defaults ─────────────────────────────────────────────────────────────────


def default_term_name(today: date | None = None) -> str:
    """Heuristic next SCU quarter when README/HANDOFF do not pin a term."""
    d = today or date.today()
    y, m = d.year, d.month
    if m <= 3:
        return f"Spring {y}"
    if m <= 8:
        return f"Fall {y}"
    return f"Winter {y + 1}"


def default_academic_level() -> str:
    return os.environ.get(_LEVEL_ENV, "Undergraduate").strip() or "Undergraduate"


# ── Atomic write & validation (unit-tested) ──────────────────────────────────


def atomic_write_xlsx(dest: Path, data: bytes) -> None:
    """Write ``dest`` via a sibling ``.tmp`` file and ``os.replace``."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, dest)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise


def validate_sections_xlsx(path: Path) -> int:
    """Parse ``path``; return course count. Raise if zero courses."""
    courses = list_offered_courses(path)
    n = len(courses)
    if n == 0:
        raise SectionsValidationError(
            f"{path} parsed to 0 offered courses — export is empty or Workday "
            "layout/filters changed. Not overwriting the shared catalog."
        )
    return n


# ── Workday navigation (fragile DOM — comments document assumptions) ─────────


def _page_heading_lower(page: Any) -> str:
    try:
        title = (page.title() or "").lower()
        heading = page.evaluate(
            "() => (document.querySelector('h1, [role=\"heading\"]') || {})"
            ".textContent || ''"
        )
        return f"{title} {str(heading).lower()}"
    except Exception:  # noqa: BLE001
        return (page.title() or "").lower()


def on_find_course_sections_page(page: Any) -> bool:
    blob = _page_heading_lower(page)
    return any(h in blob for h in _SECTIONS_HEADINGS)


def _try_global_search(page: Any, query: str) -> bool:
    """Workday universal search → open *Find Course Sections* (search fallback)."""
    box = None
    for sel in _SEARCH_BOX_SELECTORS:
        try:
            page.wait_for_selector(sel, timeout=4_000, state="visible")
            box = page.locator(sel).first
            box.click()
            break
        except Exception:  # noqa: BLE001
            box = None
    if box is None:
        return False

    try:
        box.fill(query)
        page.wait_for_timeout(1_500)
        for sel in _SEARCH_SUGGESTION_SELECTORS:
            try:
                page.locator(sel).first.click(timeout=3_000)
                page.wait_for_load_state("domcontentloaded", timeout=30_000)
                page.wait_for_timeout(wb.RENDER_WAIT_MS)
                if on_find_course_sections_page(page):
                    return True
            except Exception:  # noqa: BLE001
                continue
        page.keyboard.press("Enter")
        page.wait_for_load_state("domcontentloaded", timeout=30_000)
        page.wait_for_timeout(wb.RENDER_WAIT_MS)
        return on_find_course_sections_page(page)
    except Exception:  # noqa: BLE001
        return False


def _click_visible_text(page: Any, text: str, *, timeout: int = 3_000) -> bool:
    try:
        page.get_by_text(text, exact=False).first.click(timeout=timeout)
        return True
    except Exception:  # noqa: BLE001
        return False


def _select_filter_option(page: Any, label_keywords: tuple[str, ...], value: str) -> bool:
    """Open a filter whose label matches ``label_keywords`` and pick ``value``.

    Workday filter rows vary by tenant refresh — we try label text, combobox
    roles, and common ``data-automation-id`` patterns. Failure is non-fatal
    (caller may still get a partial export).
    """
    value_re = re.compile(re.escape(value), re.I)
    # Strategy A: filter prompt button near a label keyword
    for kw in label_keywords:
        try:
            row = page.locator(f'[data-automation-id*="filter" i]').filter(
                has_text=re.compile(kw, re.I)
            ).first
            if row.count() > 0:
                row.click(timeout=2_000)
                page.wait_for_timeout(400)
        except Exception:  # noqa: BLE001
            pass
        try:
            page.get_by_role("button", name=re.compile(kw, re.I)).first.click(timeout=2_000)
            page.wait_for_timeout(400)
        except Exception:  # noqa: BLE001
            continue

    # Strategy B: combobox / listbox option with the term/level text
    for role in ("option", "menuitem", "treeitem"):
        try:
            page.get_by_role(role, name=value_re).first.click(timeout=3_000)
            return True
        except Exception:  # noqa: BLE001
            continue

    # Strategy C: plain text match in the open panel
    if _click_visible_text(page, value):
        page.wait_for_timeout(300)
        return True

    # Strategy D: type into an active search field inside the filter popup
    try:
        active = page.locator(
            'input:focus, [data-automation-id*="search" i] input, '
            '[role="combobox"] input'
        ).first
        active.fill(value, timeout=2_000)
        page.wait_for_timeout(500)
        page.keyboard.press("Enter")
        return True
    except Exception:  # noqa: BLE001
        return False


def _run_search(page: Any) -> None:
    for sel in _SEARCH_RUN_SELECTORS:
        try:
            page.click(sel, timeout=3_000)
            page.wait_for_timeout(wb.RENDER_WAIT_MS)
            return
        except Exception:  # noqa: BLE001
            continue


def navigate_find_course_sections(
    page: Any,
    *,
    term: str,
    level: str,
    task_url: str | None,
) -> None:
    """Drive ``page`` to filtered Find Course Sections results (pre-export).

    Order: direct task URL (if set) → global search fallback → term/level
    filters → Search. Raises ``RuntimeError`` when the report cannot be reached.
    """
    if task_url:
        try:
            page.goto(task_url, wait_until="domcontentloaded", timeout=wb.NAV_TIMEOUT_MS)
            page.wait_for_timeout(wb.RENDER_WAIT_MS)
        except Exception:  # noqa: BLE001
            pass
        if on_find_course_sections_page(page):
            pass
        else:
            task_url = None  # stale task id — fall through to search

    if not on_find_course_sections_page(page):
        if not _try_global_search(page, _SEARCH_QUERY):
            actual = ""
            try:
                actual = (page.title() or "").strip()
            except Exception:  # noqa: BLE001
                pass
            raise RuntimeError(
                "Could not open Workday 'Find Course Sections'. "
                f"Currently on {actual!r}. Set "
                f"{_SECTIONS_URL_ENV} to a direct task URL or fix search selectors."
            )

    _select_filter_option(page, _TERM_FILTER_LABELS, term)
    _select_filter_option(page, _LEVEL_FILTER_LABELS, level)
    _run_search(page)


# ── Main ─────────────────────────────────────────────────────────────────────


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Pull Find Course Sections xlsx from Workday (headed browser)."
    )
    p.add_argument(
        "--term",
        default=os.environ.get(_TERM_ENV) or default_term_name(),
        help="Academic period / quarter filter text (default: upcoming quarter heuristic).",
    )
    p.add_argument(
        "--level",
        default=default_academic_level(),
        help="Academic level filter (default: Undergraduate).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate only; do not write SCU_Find_Course_Sections.xlsx.",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        from playwright.sync_api import TimeoutError as PWTimeout
    except ImportError:
        print(
            "ERROR: playwright is not installed. Run: pip install -r project/requirements.txt "
            "&& playwright install chromium",
            file=sys.stderr,
            flush=True,
        )
        return EXIT_USAGE

    args = _parse_args(argv)
    task_url = (os.environ.get(_SECTIONS_URL_ENV) or "").strip() or None

    context = None
    try:
        context, page = wb.launch(PROFILE_DIR)
        wb.wait_for_login(page)

        def _navigate(pg: Any) -> None:
            navigate_find_course_sections(
                pg,
                term=args.term.strip(),
                level=args.level.strip(),
                task_url=task_url,
            )

        data = wb.export_to_excel(page, _navigate)

        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tf:
            tmp = Path(tf.name)
            tmp.write_bytes(data)
        try:
            n = validate_sections_xlsx(tmp)
        finally:
            tmp.unlink(missing_ok=True)

        if args.dry_run:
            print(f"Dry run OK — validated {n} courses (catalog not written).", flush=True)
        else:
            atomic_write_xlsx(DEST_XLSX, data)
            print(f"Wrote {DEST_XLSX} ({n} courses).", flush=True)

        print(
            "\nReminder: restart the API or POST /api/courses/refresh so cached "
            "schedule indexes reload the new xlsx.\n",
            flush=True,
        )
        return EXIT_OK

    except SectionsValidationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr, flush=True)
        return EXIT_VALIDATION
    except TimeoutError as exc:
        print(f"ERROR: login timed out — {exc}", file=sys.stderr, flush=True)
        return EXIT_LOGIN
    except RuntimeError as exc:
        msg = str(exc).lower()
        code = EXIT_NAVIGATION if "find course sections" in msg or "open workday" in msg else EXIT_EXPORT
        print(f"ERROR: {exc}", file=sys.stderr, flush=True)
        return code
    except PWTimeout as exc:
        print(f"ERROR: Workday timed out — {exc}", file=sys.stderr, flush=True)
        return EXIT_NAVIGATION
    except OSError as exc:
        print(f"ERROR: failed to write catalog — {exc}", file=sys.stderr, flush=True)
        return EXIT_WRITE
    finally:
        if context is not None:
            try:
                context.close()
            except Exception:  # noqa: BLE001
                pass


if __name__ == "__main__":
    raise SystemExit(main())
