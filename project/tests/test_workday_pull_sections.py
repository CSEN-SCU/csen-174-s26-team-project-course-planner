"""Tests for scripts/workday_pull_sections.py (no Playwright in CI)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from scripts import workday_pull_sections as wps


def test_atomic_write_xlsx_replaces_dest(tmp_path: Path) -> None:
    dest = tmp_path / "SCU_Find_Course_Sections.xlsx"
    dest.write_bytes(b"old")
    wps.atomic_write_xlsx(dest, b"PK\x03\x04 new")
    assert dest.read_bytes() == b"PK\x03\x04 new"
    assert not dest.with_suffix(".xlsx.tmp").exists()


def test_atomic_write_cleans_tmp_on_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dest = tmp_path / "out.xlsx"
    monkeypatch.setattr(wps.os, "replace", MagicMock(side_effect=OSError("disk full")))
    with pytest.raises(OSError, match="disk full"):
        wps.atomic_write_xlsx(dest, b"x")
    assert not dest.with_suffix(".xlsx.tmp").exists()


def test_validate_sections_xlsx_returns_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = [{"course": "CSEN 20", "title": "Intro"}]
    monkeypatch.setattr(wps, "list_offered_courses", lambda _p: fake)
    n = wps.validate_sections_xlsx(tmp_path / "any.xlsx")
    assert n == 1


def test_validate_sections_xlsx_rejects_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(wps, "list_offered_courses", lambda _p: [])
    with pytest.raises(wps.SectionsValidationError, match="0 offered courses"):
        wps.validate_sections_xlsx(tmp_path / "empty.xlsx")


def test_default_term_name_spring_in_january() -> None:
    assert wps.default_term_name(date(2026, 2, 1)) == "Spring 2026"


def test_default_term_name_fall_in_may() -> None:
    assert wps.default_term_name(date(2026, 5, 24)) == "Fall 2026"


def test_default_academic_level_is_undergrad() -> None:
    assert wps.default_academic_level() == "Undergrad"


def test_academic_year_range_labels_for_fall_2026() -> None:
    labels = wps.academic_year_range_labels(2026)
    assert "2026 to 2027" in labels


def test_fall_quarter_row_labels_include_quarter_suffix() -> None:
    labels = wps.fall_quarter_row_labels("Fall 2026")
    assert "Fall 2026 Quarter (" in labels
    assert "Fall 2026" in labels


def test_close_period_flyout_clicks_period_input_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = MagicMock()
    dialog = MagicMock()
    row = MagicMock()
    dialog.locator.return_value.filter.return_value.first = row
    row.locator.return_value.first.click.return_value = None
    picker_calls = {"n": 0}

    def _picker_open(_p: object) -> bool:
        picker_calls["n"] += 1
        return picker_calls["n"] == 1

    monkeypatch.setattr(wps, "_cascading_picker_visible", _picker_open)
    wps._close_period_flyout(page, dialog)
    assert row.locator.return_value.first.click.called
    page.keyboard.press.assert_not_called()


def test_on_find_course_sections_page_detects_heading(monkeypatch: pytest.MonkeyPatch) -> None:
    page = MagicMock()
    page.title.return_value = "Find Course Sections"
    page.evaluate.return_value = ""
    monkeypatch.setattr(wps, "_find_course_filter_modal_visible", lambda _p: False)
    monkeypatch.setattr(wps.wb, "export_controls_visible", lambda _p: False)
    assert wps.on_find_course_sections_page(page) is True


def test_on_find_course_sections_page_false_on_filter_modal(monkeypatch: pytest.MonkeyPatch) -> None:
    page = MagicMock()
    page.title.return_value = "SCU Find Course Sections"
    monkeypatch.setattr(wps, "_find_course_filter_modal_visible", lambda _p: True)
    assert wps.on_find_course_sections_page(page) is False
    assert wps.at_find_course_sections_entry(page) is True


def _page_with_title(title: str, *, heading: str = ""):
    return SimpleNamespace(
        title=lambda: title,
        evaluate=lambda _js: heading,
        url="https://www.myworkday.com/scu/d/home.htmld",
        wait_for_load_state=lambda *_a, **_k: None,
        wait_for_timeout=lambda *_a, **_k: None,
        goto=lambda *_a, **_k: None,
    )


def test_ensure_find_course_sections_skips_when_already_there(monkeypatch) -> None:
    page = _page_with_title("Find Course Sections")
    page.goto = pytest.fail  # type: ignore[attr-defined]
    monkeypatch.setattr(wps, "_try_home_academics_find_course", lambda _p: pytest.fail())
    wps._ensure_find_course_sections(page, None)


def test_ensure_find_course_sections_prefers_academics_app(monkeypatch) -> None:
    page = _page_with_title("Workday Home", heading="Dashboard")
    order: list[str] = []

    monkeypatch.setattr(
        wps,
        "_try_home_academics_find_course",
        lambda _p: order.append("home") or True,
    )
    monkeypatch.setattr(wps, "_try_global_search", lambda *_a, **_k: order.append("search") or True)
    page.goto = pytest.fail  # type: ignore[attr-defined]
    monkeypatch.setattr(wps, "_wait_for_workday_content", lambda *_a, **_k: None)
    wps._ensure_find_course_sections(page, None)
    assert order == ["home"]


def test_ensure_find_course_sections_search_is_last_resort(monkeypatch) -> None:
    page = _page_with_title("Workday Home", heading="Dashboard")
    order: list[str] = []

    monkeypatch.setattr(wps, "_try_home_academics_find_course", lambda _p: False)
    monkeypatch.setattr(
        wps,
        "_try_global_search",
        lambda *_a, **_k: order.append("search") or True,
    )
    page.goto = lambda *_a, **_k: order.append("goto")  # type: ignore[attr-defined]
    monkeypatch.setattr(wps, "_wait_for_workday_content", lambda *_a, **_k: None)
    wps._ensure_find_course_sections(page, "https://example.com/task.htmld")
    assert order == ["goto", "search"]


def test_ensure_find_course_sections_raises_when_all_fail(monkeypatch) -> None:
    page = _page_with_title("Wrong Page", heading="Active Holds")
    monkeypatch.setattr(wps, "_try_home_academics_find_course", lambda _p: False)
    monkeypatch.setattr(wps, "_try_global_search", lambda *_a, **_k: False)
    monkeypatch.setattr(wps, "_wait_for_workday_content", lambda *_a, **_k: None)
    with pytest.raises(RuntimeError, match="Find Course Sections"):
        wps._ensure_find_course_sections(page, None)
