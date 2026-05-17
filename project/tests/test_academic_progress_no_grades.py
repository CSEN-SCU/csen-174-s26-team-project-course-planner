"""Academic Progress parse and persistence must never retain letter grades."""

from __future__ import annotations

import json
from io import BytesIO

import pytest
from openpyxl import Workbook

from agents import memory_agent
from utils.academic_progress_xlsx import parse_academic_progress_xlsx, sanitize_parsed_rows


def _minimal_progress_xlsx(*, include_grade: bool = True) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(["Requirement", "Status", "Remaining", "Registration", "Period", "Units", "Grade"])
    ws.append(
        [
            "Core Curriculum",
            "Satisfied",
            None,
            "COEN 10 - Intro to Programming",
            "Fall 2024",
            4,
            "A" if include_grade else None,
        ],
    )
    ws.append(
        [
            "Major Requirement",
            "Not Satisfied",
            4,
            None,
            None,
            None,
            "B+" if include_grade else None,
        ],
    )
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_parse_omits_grade_from_detail_rows():
    data = parse_academic_progress_xlsx(_minimal_progress_xlsx(include_grade=True))
    for row in data["detail_rows"]:
        assert "grade" not in row


def test_sanitize_parsed_rows_strips_grade_keys():
    raw = [{"course_code": "COEN 10", "grade": "A-", "status": "Satisfied"}]
    cleaned = sanitize_parsed_rows(raw)
    assert cleaned[0]["course_code"] == "COEN 10"
    assert "grade" not in cleaned[0]


@pytest.fixture
def temp_memory_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("COURSE_PLANNER_MEMORY_DIR", str(tmp_path))
    monkeypatch.setattr(memory_agent, "_validate_user_id", lambda uid: int(uid))
    yield tmp_path


def test_memory_write_parsed_rows_strips_grades(temp_memory_dir):
    payload = json.dumps([{"course_code": "MATH 11", "grade": "B+"}])
    memory_agent.write(1, "parsed_rows", payload)
    items = memory_agent.list_for_user(1)
    parsed = next(it for it in items if it["kind"] == "parsed_rows")
    rows = json.loads(parsed["content"])
    assert rows[0]["course_code"] == "MATH 11"
    assert "grade" not in rows[0]
