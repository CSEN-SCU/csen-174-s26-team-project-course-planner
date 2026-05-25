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


def test_on_academic_progress_page_rejects_unrelated():
    page = _page_with_title("Find Course Sections", heading="Course Catalog")
    assert wpp._on_academic_progress_page(page) is False


def test_ensure_on_task_skips_goto_when_already_there(monkeypatch):
    page = _page_with_title("View My Academic Progress")
    page.goto = pytest.fail  # type: ignore[attr-defined]
    wpp._ensure_on_task(page)  # should return without navigating


def test_ensure_on_task_raises_when_navigation_fails(monkeypatch):
    page = _page_with_title("Wrong Report", heading="Active Holds")
    page.goto = lambda *_a, **_k: None  # type: ignore[attr-defined]
    page.wait_for_load_state = lambda *_a, **_k: None  # type: ignore[attr-defined]
    page.wait_for_timeout = lambda *_a, **_k: None  # type: ignore[attr-defined]
    monkeypatch.setattr(wpp, "_try_search_for_report", lambda _p: False)
    with pytest.raises(RuntimeError, match="View My Academic Progress"):
        wpp._ensure_on_task(page, task_url=wpp.TASK_URL)


# ── CLI / upload (mocked) ─────────────────────────────────────────────────────


def test_main_save_mode_writes_file(tmp_path, monkeypatch):
    fake_bytes = _minimal_progress_xlsx()

    def _fake_pull():
        return fake_bytes

    monkeypatch.setattr(wpp, "launch", lambda _p: (_NoCloseContext(), object()))
    monkeypatch.setattr(wpp, "wait_for_login", lambda _page: None)
    monkeypatch.setattr(wpp, "export_to_excel", lambda _page, _nav: _fake_pull())

    out = tmp_path / "progress.xlsx"
    assert wpp.main(["--save", str(out)]) == 0
    assert out.read_bytes() == fake_bytes


def test_main_upload_failure_returns_1(monkeypatch):
    monkeypatch.setattr(wpp, "launch", lambda _p: (_NoCloseContext(), object()))
    monkeypatch.setattr(wpp, "wait_for_login", lambda _page: None)
    monkeypatch.setattr(
        wpp,
        "export_to_excel",
        lambda _page, _nav: _minimal_progress_xlsx(),
    )

    def _boom(**_kw):
        raise ConnectionError("API down")

    monkeypatch.setattr(wpp, "_post_transcript", _boom)
    assert wpp.main(["--user-id", "u-test"]) == 1


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
