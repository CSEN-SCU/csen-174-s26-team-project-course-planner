#!/usr/bin/env python3
"""Admin CLI: refresh the shared next-term *Find Course Sections* catalog.

Opens a **headed** Chromium window; a human completes SCU SSO + Duo. The script
then navigates to Find Course Sections, applies term/level filters, exports to
Excel, validates the download, and atomically overwrites
``SCU_Find_Course_Sections.xlsx``.

Usage (from ``project/course_planner/``)::

    python scripts/workday_pull_sections.py
    python scripts/workday_pull_sections.py --term "Fall 2026" --level Undergrad

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
from collections.abc import Callable
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
from scripts.workday_pull_progress import (  # noqa: E402
    _any_visible,
    _click_labels,
    _wait_for_workday_content,
)
from utils.scu_course_schedule_xlsx import (  # noqa: E402
    clear_schedule_caches,
    list_offered_courses,
)

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
# SCU Academics hub: right-hand app tile (not the top global search box).
_FIND_COURSE_APP_LABELS = (
    "SCU Find Course",
    "SU Find Course",
    "Find Course",
    "Find Course Sections",
)
_FIND_COURSE_TILE_SELECTORS = (
    '[aria-label*="Find Course" i]',
    '[aria-label*="SCU Find" i]',
    '[data-automation-id*="app" i][aria-label*="Course" i]',
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
    """SCU Workday label for undergraduate students (not 'Undergraduate')."""
    return os.environ.get(_LEVEL_ENV, "Undergrad").strip() or "Undergrad"


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


def _find_course_filter_modal_visible(page: Any) -> bool:
    """True on the SCU filter dialog (Academic Period / Level) before results load."""
    try:
        dialog = page.get_by_role("dialog").filter(
            has=page.get_by_text(re.compile(r"SCU Find Course Sections|Find Course Sections", re.I))
        )
        if not dialog.first.is_visible(timeout=1_000):
            return False
        return dialog.get_by_text(re.compile(r"Academic\s+Level", re.I)).first.is_visible(
            timeout=800
        )
    except Exception:  # noqa: BLE001
        return False


def on_find_course_sections_page(page: Any) -> bool:
    """True on the results/report view — not the pre-search filter modal."""
    if _find_course_filter_modal_visible(page):
        return False
    if wb.export_controls_visible(page):
        return True
    blob = _page_heading_lower(page)
    return any(h in blob for h in _SECTIONS_HEADINGS)


def at_find_course_sections_entry(page: Any) -> bool:
    """Filter modal or results page — navigation succeeded past the app tile."""
    return _find_course_filter_modal_visible(page) or on_find_course_sections_page(page)


def _click_find_course_sections_entry(page: Any) -> bool:
    """Open Find Course Sections when its link or app tile is already visible."""

    def _ready() -> bool:
        return at_find_course_sections_entry(page)

    for label in _FIND_COURSE_APP_LABELS:
        if _click_labels(page, (label,), role="link", ready=_ready):
            return at_find_course_sections_entry(page)
        if _click_labels(page, (label,), ready=_ready):
            return at_find_course_sections_entry(page)

    for sel in _FIND_COURSE_TILE_SELECTORS:
        try:
            tile = page.locator(sel).first
            tile.wait_for(state="visible", timeout=1_500)
            tile.click(timeout=5_000)
            page.wait_for_timeout(400)
            _wait_for_workday_content(page, _ready)
            if at_find_course_sections_entry(page):
                return True
        except Exception:  # noqa: BLE001
            continue
    return False


def _try_home_academics_find_course(page: Any) -> bool:
    """SCU home: Academics → View More → SCU Find Course app tile (proven SCU path)."""
    print(
        "Trying home: Academics → View More → SCU Find Course…",
        flush=True,
    )
    _wait_for_workday_content(page, _any_visible(page, "Academics", "SCU Academics"))

    after_academics = _any_visible(
        page, "View More", "View All Apps", "Find Course", "SCU Find Course"
    )
    if not _click_labels(
        page, ("Academics", "SCU Academics"), role="link", ready=after_academics
    ):
        if not _click_labels(page, ("Academics",), ready=after_academics):
            return False

    find_course_panel = _any_visible(
        page,
        "SCU Find Course",
        "SU Find Course",
        "Find Course",
        "Find Course Sections",
        "View More",
    )
    _click_labels(
        page,
        ("View More", "View All Apps", "View All Apps >", "View All"),
        ready=find_course_panel,
    )
    return _click_find_course_sections_entry(page)


def _ensure_find_course_sections(page: Any, task_url: str | None) -> None:
    """Navigate to Find Course Sections (Academics app menu first — matches progress pull)."""
    print("Navigating to Find Course Sections…", flush=True)

    def _home_or_report() -> bool:
        if at_find_course_sections_entry(page):
            return True
        return _any_visible(page, "Academics", "SCU Academics")()

    _wait_for_workday_content(page, _home_or_report)
    if at_find_course_sections_entry(page):
        print("Already on Find Course Sections (filter modal or report).", flush=True)
        return

    # Fast path: tile/link visible on the current hub (right-hand apps panel).
    try:
        if _any_visible(page, *_FIND_COURSE_APP_LABELS)():
            if _click_find_course_sections_entry(page):
                print("Reached Find Course Sections via direct app link.", flush=True)
                return
    except Exception:  # noqa: BLE001
        pass

    if _try_home_academics_find_course(page):
        print("Reached Find Course Sections via Academics app menu.", flush=True)
        return

    url = (task_url or "").strip()
    if url:
        print("Opening task URL…", flush=True)
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=wb.NAV_TIMEOUT_MS)
            _wait_for_workday_content(page, lambda: on_find_course_sections_page(page))
        except Exception:  # noqa: BLE001
            pass
        if on_find_course_sections_page(page):
            print("Reached Find Course Sections via task URL.", flush=True)
            return

        if _try_home_academics_find_course(page):
            print(
                "Reached Find Course Sections via Academics app menu (after task URL).",
                flush=True,
            )
            return

    print(
        "Task URL did not land on the report — trying Workday global search (last resort)…",
        flush=True,
    )
    if _try_global_search(page, _SEARCH_QUERY):
        print("Reached Find Course Sections via search.", flush=True)
        return

    actual = ""
    try:
        actual = (page.title() or "").strip()
    except Exception:  # noqa: BLE001
        pass
    raise RuntimeError(
        "Could not open Workday 'Find Course Sections'"
        + (f" — currently on {actual!r}." if actual else ".")
        + f"\nSet {_SECTIONS_URL_ENV} to a direct task URL, or open "
        "Academics → View More → SCU Find Course manually and re-run."
    )


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


_PROMPT_ICON_SELECTORS = (
    '[data-automation-id="promptIcon"]',
    '[data-automation-id="prompt"]',
    'button[aria-label*="Open" i]',
    'button[title*="Open" i]',
)


def _find_course_sections_dialog(page: Any) -> Any | None:
    if not _find_course_filter_modal_visible(page):
        return None
    try:
        return page.get_by_role("dialog").filter(
            has=page.get_by_text(re.compile(r"SCU Find Course Sections|Find Course Sections", re.I))
        ).first
    except Exception:  # noqa: BLE001
        return None


def _open_modal_field_prompt(page: Any, dialog: Any, label_pattern: str) -> bool:
    """Click the list/prompt icon to the right of a labeled field in the filter modal."""
    label_re = re.compile(label_pattern, re.I)
    containers = (
        dialog.locator('[data-automation-id="formElement"]').filter(has_text=label_re),
        dialog.locator('[data-automation-id="multiselectInputContainer"]').filter(
            has_text=label_re
        ),
        dialog.locator("div").filter(has_text=label_re),
    )
    for container in containers:
        try:
            if container.count() == 0:
                continue
            box = container.first
            for sel in _PROMPT_ICON_SELECTORS:
                btn = box.locator(sel).first
                if btn.is_visible(timeout=800):
                    btn.click(timeout=3_000)
                    page.wait_for_timeout(500)
                    return True
            inp = box.locator("input").first
            if inp.is_visible(timeout=500):
                inp.click(timeout=2_000)
            for sel in _PROMPT_ICON_SELECTORS:
                btn = box.locator(sel).first
                if btn.is_visible(timeout=800):
                    btn.click(timeout=3_000)
                    page.wait_for_timeout(500)
                    return True
        except Exception:  # noqa: BLE001
            continue
    try:
        label = dialog.get_by_text(label_re).first
        row = label.locator(
            "xpath=ancestor::*[contains(@data-automation-id,'formElement')][1]"
        )
        for sel in _PROMPT_ICON_SELECTORS:
            btn = row.locator(sel).first
            if btn.is_visible(timeout=800):
                btn.click(timeout=3_000)
                page.wait_for_timeout(500)
                return True
    except Exception:  # noqa: BLE001
        pass
    return False


def _pick_list_option(page: Any, *candidates: str) -> bool:
    """Pick one of ``candidates`` from the open Workday list/prompt popup."""
    for value in candidates:
        if _click_prompt_row(page, value):
            return True
    return False


def _parse_fall_year(term: str) -> int | None:
    m = re.search(r"Fall\s*(\d{4})", term.strip(), re.I)
    return int(m.group(1)) if m else None


def academic_year_range_labels(fall_year: int) -> tuple[str, ...]:
    """SCU nests Fall under the academic year spanning fall_year → fall_year+1."""
    y, y1 = fall_year, fall_year + 1
    return tuple(
        dict.fromkeys(
            (
                f"{y} to {y1}",
                f"{y} - {y1}",
                f"{y}-{y1}",
                f"{y}/{y1}",
                f"{y} – {y1}",
            )
        )
    )


def fall_quarter_row_labels(term: str) -> tuple[str, ...]:
    """Row text for the Fall quarter leaf (SCU shows dates in parentheses)."""
    cleaned = term.strip()
    m = re.match(r"Fall\s*(\d{4})", cleaned, re.I)
    if not m:
        return (cleaned,)
    year = m.group(1)
    yy = year[-2:]
    y1 = str(int(yy) + 1).zfill(2)
    return tuple(
        dict.fromkeys(
            (
                f"Fall {year} Quarter (",
                f"Fall {year} quarter",
                f"Fall {year} Quarter",
                f"Fall Quarter {year}",
                f"Fall {year}",
                cleaned,
                f"Fall Quarter {yy}-{y1}",
            )
        )
    )


_PROMPT_ROW_SELECTORS = (
    '[data-automation-id="promptOption"]',
    '[data-automation-id="menuItem"]',
    '[data-automation-id="activeListRow"]',
    '[data-automation-id="treeViewNode"]',
    '[data-automation-id="normalRow"]',
    '[role="menuitem"]',
    '[role="treeitem"]',
    "li",
)


def _cascading_picker_visible(page: Any) -> bool:
    """True while the Academic Period list / columns are still open on screen."""
    try:
        if page.locator('[data-automation-id="promptOption"]').first.is_visible(timeout=400):
            return True
    except Exception:  # noqa: BLE001
        pass
    try:
        if page.locator('[data-automation-id="activeListRow"]').first.is_visible(timeout=400):
            return True
    except Exception:  # noqa: BLE001
        pass
    popup_selectors = (
        '[data-automation-id="popUpDialog"]',
        '[data-automation-id="wd-popup"]',
    )
    for sel in popup_selectors:
        try:
            popup = page.locator(sel).first
            if popup.is_visible(timeout=400) and page.locator(
                '[data-automation-id="promptOption"]'
            ).first.is_visible(timeout=300):
                return True
        except Exception:  # noqa: BLE001
            continue
    return False


def _academic_period_shows_fall(dialog: Any, fall_year: int) -> bool:
    """True when the period field shows a selected Fall chip (checkbox step succeeded)."""
    try:
        row = dialog.locator('[data-automation-id="formElement"]').filter(
            has_text=re.compile(r"Academic\s+Period", re.I)
        ).first
        text = row.inner_text(timeout=2_000)
        return bool(re.search(rf"Fall\s+{fall_year}", text, re.I))
    except Exception:  # noqa: BLE001
        return False


def _require_filter_modal(page: Any, step: str) -> None:
    if not _find_course_filter_modal_visible(page):
        raise RuntimeError(
            f"The SCU Find Course Sections filter window closed unexpectedly {step}. "
            "Click the Academic Period box (not Escape) to collapse the period list."
        )


def _collapse_field_input(page: Any, dialog: Any, label_pattern: str) -> None:
    """Click a modal field's text box (not the list icon) — commits selection and closes flyouts."""
    try:
        row = dialog.locator('[data-automation-id="formElement"]').filter(
            has_text=re.compile(label_pattern, re.I)
        ).first
        row.locator("input").first.click(timeout=2_000)
        page.wait_for_timeout(500)
    except Exception:  # noqa: BLE001
        pass


def _close_period_flyout(page: Any, dialog: Any) -> None:
    """Collapse the period dropdown so Academic Level is clickable (never press Escape)."""
    if not _cascading_picker_visible(page):
        return
    print("Closing Academic Period list (click outside, not Escape)…", flush=True)
    _collapse_field_input(page, dialog, r"Academic\s+Period")
    page.wait_for_timeout(400)
    if not _cascading_picker_visible(page):
        return
    for target in (
        dialog.get_by_text(re.compile(r"Filter Name", re.I)).first,
        dialog.get_by_text(re.compile(r"Academic\s+Level", re.I)).first,
    ):
        try:
            target.click(timeout=2_000)
            page.wait_for_timeout(500)
            if not _cascading_picker_visible(page):
                return
        except Exception:  # noqa: BLE001
            continue
    try:
        page.keyboard.press("Tab")
        page.wait_for_timeout(400)
    except Exception:  # noqa: BLE001
        pass


def _open_modal_field_prompt_with_retry(
    page: Any,
    dialog: Any,
    label_pattern: str,
    *,
    close_period_first: bool = True,
    attempts: int = 4,
) -> bool:
    for _ in range(attempts):
        if close_period_first:
            _close_period_flyout(page, dialog)
        if _open_modal_field_prompt(page, dialog, label_pattern):
            return True
        page.wait_for_timeout(400)
    return False


def _click_prompt_row_in(page: Any, root: Any, text: str) -> bool:
    """Click a row in an open Workday prompt list (scoped to ``root`` when possible)."""
    if not text:
        return False
    label_re = re.compile(re.escape(text), re.I)
    for sel in _PROMPT_ROW_SELECTORS:
        try:
            row = root.locator(sel).filter(has_text=label_re).first
            row.scroll_into_view_if_needed(timeout=2_000)
            row.click(timeout=3_000)
            page.wait_for_timeout(500)
            return True
        except Exception:  # noqa: BLE001
            continue
    for role in ("menuitem", "treeitem", "option", "button"):
        try:
            root.get_by_role(role, name=label_re).first.click(timeout=3_000)
            page.wait_for_timeout(500)
            return True
        except Exception:  # noqa: BLE001
            continue
    try:
        el = root.get_by_text(label_re, exact=False).first
        el.scroll_into_view_if_needed(timeout=2_000)
        el.hover(timeout=2_000)
        page.wait_for_timeout(300)
        el.click(timeout=3_000)
        page.wait_for_timeout(500)
        return True
    except Exception:  # noqa: BLE001
        return False


def _click_prompt_row(page: Any, text: str) -> bool:
    """Click a row in the open Workday prompt / cascading list popup."""
    if _click_prompt_row_in(page, page, text):
        return True
    try:
        popup = page.locator('[data-automation-id="popUpDialog"], [data-automation-id="wd-popup"]').last
        if popup.is_visible(timeout=500):
            return _click_prompt_row_in(page, popup, text)
    except Exception:  # noqa: BLE001
        pass
    return False


def _click_prompt_row_matching(page: Any, root: Any, pattern: re.Pattern[str]) -> bool:
    for sel in _PROMPT_ROW_SELECTORS:
        try:
            row = root.locator(sel).filter(has_text=pattern).first
            row.scroll_into_view_if_needed(timeout=2_000)
            row.click(timeout=3_000)
            page.wait_for_timeout(500)
            return True
        except Exception:  # noqa: BLE001
            continue
    try:
        root.get_by_text(pattern).first.click(timeout=3_000)
        page.wait_for_timeout(500)
        return True
    except Exception:  # noqa: BLE001
        return False


_LEVEL_ROW_PATTERNS = (
    re.compile(r"^Undergrad\b", re.I),
    re.compile(r"^Undergraduate\b", re.I),
    re.compile(r"^UG\b", re.I),
)


def _academic_level_shows_undergrad(dialog: Any) -> bool:
    try:
        row = dialog.locator('[data-automation-id="formElement"]').filter(
            has_text=re.compile(r"Academic\s+Level", re.I)
        ).first
        return bool(re.search(r"undergrad", row.inner_text(timeout=2_000), re.I))
    except Exception:  # noqa: BLE001
        return False


def _pick_academic_level(page: Any, dialog: Any, level: str) -> bool:
    """Select Undergrad in the Academic Level prompt (flat list, often with checkboxes)."""
    print("Selecting Academic Level: Undergrad…", flush=True)
    literal_choices = tuple(
        dict.fromkeys([level.strip(), "Undergrad", "Undergraduate", "UG"])
    )
    scopes: list[Any] = [page]
    try:
        popup = page.locator('[data-automation-id="popUpDialog"], [data-automation-id="wd-popup"]').last
        if popup.is_visible(timeout=800):
            scopes.insert(0, popup)
    except Exception:  # noqa: BLE001
        pass
    scopes.append(dialog)

    for scope in scopes:
        for choice in literal_choices:
            if _click_prompt_row_in(page, scope, choice):
                page.wait_for_timeout(400)
                if _academic_level_shows_undergrad(dialog):
                    return True
        for pat in _LEVEL_ROW_PATTERNS:
            if _click_prompt_row_matching(page, scope, pat):
                page.wait_for_timeout(400)
                if _academic_level_shows_undergrad(dialog):
                    return True

    try:
        search = page.locator(
            '[data-automation-id="searchBox"] input, '
            '[data-automation-id*="search" i] input, '
            'input[placeholder*="Search" i]'
        ).last
        if search.is_visible(timeout=1_000):
            search.fill("Undergrad", timeout=2_000)
            page.wait_for_timeout(600)
            for scope in scopes:
                if _click_prompt_row_in(page, scope, "Undergrad"):
                    page.wait_for_timeout(400)
                    if _academic_level_shows_undergrad(dialog):
                        return True
    except Exception:  # noqa: BLE001
        pass

    return _academic_level_shows_undergrad(dialog)


def _pick_future_fall_period(page: Any, term: str) -> bool:
    """Future Periods → 2026 to 2027 → Fall 2026 quarter (SCU nested prompt)."""
    fall_year = _parse_fall_year(term)
    if fall_year is None:
        return _pick_list_option(page, term)

    print(
        f"Selecting academic period: Future Periods → "
        f"{academic_year_range_labels(fall_year)[0]} → Fall {fall_year}…",
        flush=True,
    )

    if not _click_prompt_row(page, "Future Periods"):
        if not _click_prompt_row(page, "Future Period"):
            return False

    year_labels = academic_year_range_labels(fall_year)
    year_opened = False
    for yr in year_labels:
        if _click_prompt_row(page, yr):
            year_opened = True
            break
    if not year_opened:
        # Some builds need hover on Future Periods before the year column appears.
        try:
            page.get_by_text(re.compile(r"Future\s+Periods?", re.I)).first.hover(
                timeout=2_000
            )
            page.wait_for_timeout(400)
        except Exception:  # noqa: BLE001
            pass
        for yr in year_labels:
            if _click_prompt_row(page, yr):
                year_opened = True
                break
    if not year_opened:
        return False

    fall_row_re = re.compile(rf"Fall\s+{fall_year}\s+Quarter\s*\(", re.I)
    try:
        row = page.locator(
            '[data-automation-id="promptOption"], [data-automation-id="activeListRow"], '
            '[role="menuitem"], [role="treeitem"]'
        ).filter(has_text=fall_row_re).first
        row.scroll_into_view_if_needed(timeout=2_000)
        row.click(timeout=3_000)
        page.wait_for_timeout(600)
        return True
    except Exception:  # noqa: BLE001
        pass

    for quarter_label in fall_quarter_row_labels(term):
        if _click_prompt_row(page, quarter_label):
            return True

    fall_re = re.compile(rf"Fall\s+{fall_year}\s+Quarter", re.I)
    try:
        page.get_by_text(fall_re).first.click(timeout=3_000)
        page.wait_for_timeout(600)
        return True
    except Exception:  # noqa: BLE001
        return False


def _submit_find_course_modal(page: Any, dialog: Any) -> bool:
    for target in (
        dialog.get_by_role("button", name="OK").first,
        dialog.locator('[data-automation-id="uic_primaryButton"]').first,
        dialog.locator('button:has-text("OK")').first,
    ):
        try:
            target.click(timeout=5_000)
            page.wait_for_timeout(wb.RENDER_WAIT_MS)
            return True
        except Exception:  # noqa: BLE001
            continue
    return False


def _apply_find_course_section_filters(page: Any, term: str, level: str) -> None:
    """Fill the SCU Find Course Sections modal and click OK (May → Future Fall)."""
    dialog = _find_course_sections_dialog(page)
    if dialog is None:
        print("No filter modal — using legacy in-page filters…", flush=True)
        _select_filter_option(page, _TERM_FILTER_LABELS, term)
        _select_filter_option(page, _LEVEL_FILTER_LABELS, level)
        _run_search(page)
        return

    print(
        f"Applying SCU Find Course Sections modal: term={term!r}, level={level!r}…",
        flush=True,
    )
    level_choices = tuple(dict.fromkeys([level.strip(), "Undergrad", "Undergraduate"]))

    # SCU flow: Academic Period first, then Academic Level, then OK.
    if not _open_modal_field_prompt(page, dialog, r"Academic\s+Period"):
        raise RuntimeError(
            "Could not open the Academic Period picker (list icon) in the "
            "SCU Find Course Sections modal."
        )
    if not _pick_future_fall_period(page, term):
        raise RuntimeError(
            f"Could not select {term!r} via Future Periods → academic year → "
            "Fall quarter in Workday. Confirm the row labels in the picker."
        )

    fall_year = _parse_fall_year(term)
    if fall_year and not _academic_period_shows_fall(dialog, fall_year):
        print(
            f"WARNING: Fall {fall_year} chip not visible in Academic Period field yet.",
            flush=True,
        )

    # List stays open after the checkbox — click outside (never Escape) before Level.
    _close_period_flyout(page, dialog)
    page.wait_for_timeout(800)

    if not _find_course_filter_modal_visible(page):
        raise RuntimeError(
            "The filter window closed right after selecting Fall quarter. "
            "Do not press Escape — the script no longer uses it on this step."
        )
    dialog = _find_course_sections_dialog(page)
    if dialog is None:
        raise RuntimeError(
            "SCU Find Course Sections filter modal disappeared after selecting the term."
        )

    print("Opening Academic Level picker…", flush=True)
    if not _open_modal_field_prompt_with_retry(
        page, dialog, r"Academic\s+Level", close_period_first=False
    ):
        raise RuntimeError(
            "Could not open the Academic Level picker after selecting the term. "
            "The period list may still be open — try clicking outside it, then re-run."
        )
    page.wait_for_timeout(500)
    if not _pick_academic_level(page, dialog, level):
        raise RuntimeError(
            f"Could not select academic level {level!r} in Workday "
            f"(tried {level_choices}). Open the level list and confirm the exact row label."
        )
    _close_period_flyout(page, dialog)
    page.wait_for_timeout(400)

    print("Clicking OK on filter modal…", flush=True)
    if not _submit_find_course_modal(page, dialog):
        raise RuntimeError("Could not click OK on the SCU Find Course Sections filter modal.")

    def _results_ready() -> bool:
        if _find_course_filter_modal_visible(page):
            return False
        return wb.export_controls_visible(page) or on_find_course_sections_page(page)

    _wait_for_workday_content(page, _results_ready)


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
    progress_cb: Callable[[str], None] | None = None,
) -> None:
    """Drive ``page`` to filtered Find Course Sections results (pre-export).

    Order: Academics app menu (SCU Find Course tile) → task URL → global search
    (last resort) → term/level filters → Search. Raises ``RuntimeError`` when the
    report cannot be reached.
    """
    _ensure_find_course_sections(page, task_url)
    if progress_cb is not None:
        progress_cb("filtering")
    _apply_find_course_section_filters(page, term, level)


# ── Reusable pull (CLI + API share this) ─────────────────────────────────────


def _export_sections_bytes(
    *,
    term: str,
    level: str,
    task_url: str | None,
    profile_dir: Path,
    progress_cb: Callable[[str], None] | None = None,
) -> bytes:
    """Headed login + navigate Find Course Sections + Export to Excel → raw bytes.

    Opens the browser, blocks on human SSO + Duo, drives the report, and captures
    Workday's native export. Does **not** validate or write — callers decide.
    ``progress_cb`` receives coarse status codes (``navigating``/``exporting``…)
    plus the ``browser_open``/``logged_in`` codes emitted by ``wait_for_login``.
    """

    def _cb(status: str) -> None:
        if progress_cb is not None:
            progress_cb(status)

    context = None
    try:
        context, page = wb.launch(profile_dir)
        page = wb.wait_for_login(page, progress_cb=progress_cb)
        print("Exporting Find Course Sections to Excel…", flush=True)

        def _navigate(pg: Any) -> None:
            _cb("navigating")
            navigate_find_course_sections(
                pg,
                term=term,
                level=level,
                task_url=task_url,
                progress_cb=progress_cb,
            )

        _cb("downloading")

        def _export_poll() -> None:
            _cb("exporting")

        return wb.export_to_excel(page, _navigate, on_poll=_export_poll)
    finally:
        if context is not None:
            try:
                context.close()
            except Exception:  # noqa: BLE001
                pass


def pull_course_sections(
    *,
    term: str | None = None,
    level: str | None = None,
    task_url: str | None = None,
    profile_dir: Path | None = None,
    progress_cb: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Pull the shared *Find Course Sections* catalog and overwrite the xlsx.

    The course-availability analogue of ``pull_academic_progress``: where that
    writes per-user memory, this overwrites the **shared**
    ``SCU_Find_Course_Sections.xlsx`` (course availability is the same for every
    student) and drops in-process schedule caches so the next read reloads it.

    ``term`` / ``level`` / ``task_url`` fall back to the same env vars and
    heuristics as the CLI. Returns ``{"count", "term", "level"}``. Raises
    ``SectionsValidationError`` if the export parses to zero courses (the shared
    catalog is left untouched), or ``TimeoutError`` / ``RuntimeError`` on login
    or navigation failure.
    """

    def _cb(status: str) -> None:
        if progress_cb is not None:
            progress_cb(status)

    term_v = (term or os.environ.get(_TERM_ENV) or default_term_name()).strip()
    level_v = (level or default_academic_level()).strip()
    url_v = (
        task_url if task_url is not None else os.environ.get(_SECTIONS_URL_ENV) or ""
    ).strip() or None

    _cb("pending")
    data = _export_sections_bytes(
        term=term_v,
        level=level_v,
        task_url=url_v,
        profile_dir=profile_dir or PROFILE_DIR,
        progress_cb=progress_cb,
    )

    _cb("validating")
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tf:
        tmp = Path(tf.name)
        tmp.write_bytes(data)
    try:
        n = validate_sections_xlsx(tmp)
    finally:
        tmp.unlink(missing_ok=True)

    _cb("writing")
    atomic_write_xlsx(DEST_XLSX, data)
    # In-process only; the API process clears its own caches after the job.
    clear_schedule_caches()
    return {"count": n, "term": term_v, "level": level_v}


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
        help="Academic level filter (default: Undergrad).",
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

    try:
        data = _export_sections_bytes(
            term=args.term.strip(),
            level=args.level.strip(),
            task_url=task_url,
            profile_dir=PROFILE_DIR,
        )

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


if __name__ == "__main__":
    raise SystemExit(main())
