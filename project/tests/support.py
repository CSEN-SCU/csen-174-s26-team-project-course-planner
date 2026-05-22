"""Shared helpers for pytest modules (not collected as tests)."""

from __future__ import annotations

from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_SCHEDULE_XLSX = _PROJECT_ROOT / "course_planner" / "SCU_Find_Course_Sections.xlsx"


def schedule_xlsx_available() -> bool:
    """True when the gitignored Find Course Sections export is on disk."""
    return _SCHEDULE_XLSX.is_file()
