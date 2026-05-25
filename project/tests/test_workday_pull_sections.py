"""Tests for scripts/workday_pull_sections.py (no Playwright in CI)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
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


def test_on_find_course_sections_page_detects_heading() -> None:
    page = MagicMock()
    page.title.return_value = "Find Course Sections"
    page.evaluate.return_value = ""
    assert wps.on_find_course_sections_page(page) is True
