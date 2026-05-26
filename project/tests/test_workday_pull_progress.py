"""Tests for scripts/workday_pull_progress.py (no real Playwright in CI)."""

from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace

import pytest
from openpyxl import Workbook

from scripts import workday_pull_progress as wpp


def _empty_progress_xlsx() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(["Requirement", "Status", "Remaining", "Registration", "Period", "Units", "Grade"])
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _minimal_progress_xlsx() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(["Requirement", "Status", "Remaining", "Registration", "Period", "Units", "Grade"])
    ws.append(
        [
            "Core Curriculum",
            "Satisfied",
            None,
            "COEN 10 - Intro",
            "Fall 2024",
            4,
            None,
        ],
    )
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ── Validation ────────────────────────────────────────────────────────────────


def test_validate_progress_export_aborts_on_empty_parse():
    with pytest.raises(wpp.ProgressValidationError, match="ZERO rows"):
        wpp.validate_progress_export(_empty_progress_xlsx())


def test_validate_progress_export_accepts_nonempty():
    data = wpp.validate_progress_export(_minimal_progress_xlsx())
    assert data["detail_rows"]


# ── Page heuristics (mocked page) ───────────────────────────────────────────


def _page_with_title(title: str, *, heading: str = ""):
    return SimpleNamespace(
        title=lambda: title,
        evaluate=lambda _js: heading,
        url="https://www.myworkday.com/scu/d/task/2998$44123.htmld",
        wait_for_load_state=lambda *_a, **_k: None,
        wait_for_timeout=lambda *_a, **_k: None,
    )


def test_on_academic_progress_page_title_match():
    page = _page_with_title("View My Academic Progress")
    assert wpp._on_academic_progress_page(page) is True


def test_on_academic_progress_page_heading_match():
    page = _page_with_title("Workday", heading="My Academic Progress")
    assert wpp._on_academic_progress_page(page) is True


def test_on_academic_progress_page_rejects_academics_hub_title():
    page = _page_with_title("Academics", heading="Your Apps")
    assert wpp._on_academic_progress_page(page) is False


def test_on_academic_progress_page_rejects_unrelated():
    page = _page_with_title("Find Course Sections", heading="Course Catalog")
    assert wpp._on_academic_progress_page(page) is False


def test_on_academic_progress_page_false_while_student_modal_open(monkeypatch):
    page = _page_with_title("View My Academic Progress", heading="View My Academic Progress")
    monkeypatch.setattr(wpp, "_student_selection_modal_visible", lambda _p: True)
    assert wpp._on_academic_progress_page(page) is False


def test_ensure_on_task_skips_goto_when_already_there(monkeypatch):
    page = _page_with_title("View My Academic Progress")
    page.goto = pytest.fail  # type: ignore[attr-defined]
    monkeypatch.setattr(wpp, "_finalize_report_page", lambda _p: True)
    wpp._ensure_on_task(page)  # should return without navigating


def test_ensure_on_task_prefers_home_academics_app(monkeypatch):
    page = _page_with_title("Workday Home", heading="Dashboard")
    order: list[str] = []

    monkeypatch.setattr(
        wpp,
        "_try_home_academics_app",
        lambda _p: order.append("home") or True,
    )
    monkeypatch.setattr(
        wpp,
        "_try_sidebar_menu",
        lambda _p: order.append("sidebar") or True,
    )
    page.goto = pytest.fail  # type: ignore[attr-defined]
    page.wait_for_timeout = lambda *_a, **_k: None  # type: ignore[attr-defined]
    monkeypatch.setattr(wpp, "_finalize_report_page", lambda _p: False)
    monkeypatch.setattr(wpp, "_wait_for_workday_content", lambda *_a, **_k: None)
    wpp._ensure_on_task(page)
    assert order == ["home"]


def test_ensure_on_task_raises_when_navigation_fails(monkeypatch):
    page = _page_with_title("Wrong Report", heading="Active Holds")
    page.goto = lambda *_a, **_k: None  # type: ignore[attr-defined]
    page.wait_for_load_state = lambda *_a, **_k: None  # type: ignore[attr-defined]
    page.wait_for_timeout = lambda *_a, **_k: None  # type: ignore[attr-defined]
    monkeypatch.setattr(wpp, "_finalize_report_page", lambda _p: False)
    monkeypatch.setattr(wpp, "_wait_for_workday_content", lambda *_a, **_k: None)
    monkeypatch.setattr(wpp, "_try_home_academics_app", lambda _p: False)
    monkeypatch.setattr(wpp, "_try_sidebar_menu", lambda _p: False)
    monkeypatch.setattr(wpp, "_try_search_for_report", lambda _p: False)
    with pytest.raises(RuntimeError, match="View My Academic Progress"):
        wpp._ensure_on_task(page, task_url=wpp.TASK_URL)


# ── Conditional render wait (the perf fix) ───────────────────────────────────


def _wait_probe_page():
    timeouts: list[int] = []
    page = SimpleNamespace(
        wait_for_load_state=lambda *_a, **_k: None,
        wait_for_timeout=lambda ms: timeouts.append(ms),
    )
    return page, timeouts


def test_wait_returns_immediately_when_ready():
    """The win: stop the moment the next view is painted, don't sleep the cap."""
    page, timeouts = _wait_probe_page()
    wpp._wait_for_workday_content(page, ready=lambda: True)
    assert timeouts == []  # never paused — ready on the first check


def test_wait_falls_back_to_fixed_pause_without_ready():
    """No readiness check given → preserve the legacy fixed RENDER_WAIT_MS pause."""
    page, timeouts = _wait_probe_page()
    wpp._wait_for_workday_content(page)
    assert timeouts == [wpp.RENDER_WAIT_MS]


def test_wait_caps_when_never_ready():
    """Unmet readiness must still wait out the cap — no worse than the old behavior."""
    page, timeouts = _wait_probe_page()
    wpp._wait_for_workday_content(page, ready=lambda: False)
    assert sum(timeouts) >= wpp.RENDER_WAIT_MS


# ── CLI / upload (mocked) ─────────────────────────────────────────────────────


def test_main_save_mode_writes_file(tmp_path, monkeypatch):
    fake_bytes = _minimal_progress_xlsx()

    def _fake_pull():
        return fake_bytes

    monkeypatch.setattr(wpp, "launch", lambda _p: (_NoCloseContext(), object()))
    monkeypatch.setattr(wpp, "wait_for_login", lambda page: page)
    monkeypatch.setattr(wpp, "export_to_excel", lambda _page, _nav: _fake_pull())

    out = tmp_path / "progress.xlsx"
    assert wpp.main(["--save", str(out)]) == 0
    assert out.read_bytes() == fake_bytes


def test_main_pull_failure_returns_2(monkeypatch):
    def _boom(*_a, **_kw):
        raise ConnectionError("browser down")

    monkeypatch.setattr(wpp, "pull_academic_progress", _boom)
    assert wpp.main(["--user-id", "u-test"]) == 2


def test_main_login_timeout_returns_2(monkeypatch):
    monkeypatch.setattr(wpp, "launch", lambda _p: (_NoCloseContext(), object()))

    def _timeout(_page, **_kw):
        raise TimeoutError("login timed out")

    monkeypatch.setattr(wpp, "wait_for_login", _timeout)
    assert wpp.main(["--save", "/tmp/x.xlsx"]) == 2


def test_parser_save_takes_precedence_over_user_id():
    args = wpp._build_parser().parse_args(["--user-id", "alice", "--save", "out.xlsx"])
    assert args.save is not None
    assert args.user_id == "alice"


class _NoCloseContext:
    def close(self):
        pass
