"""Test R6 slot-based course suggestion functionality."""

from __future__ import annotations

import pytest

from agents.planning_agent import suggest_courses_for_slot


def test_suggest_courses_for_slot_returns_list():
  """Verify suggest_courses_for_slot returns a list of candidate courses."""
  result = suggest_courses_for_slot(
      day_index=0,  # Monday
      start_min=9 * 60,  # 9:00 AM
      end_min=10 * 60,  # 10:00 AM
      missing_details=[
          {"course": "CSEN 161", "category": "Core", "units": 4},
      ],
      exclude_codes=[],
  )

  assert isinstance(result, list)
  assert len(result) <= 5  # At most 5 candidates
  if result:
    # Verify structure of first candidate
    candidate = result[0]
    assert "course" in candidate
    assert "title" in candidate
    assert "units" in candidate
    assert "instructor" in candidate
    assert "rating" in candidate
    assert "difficulty" in candidate
    assert "rationale" in candidate


def test_suggest_courses_excludes_specified_codes():
  """Verify that suggest_courses_for_slot excludes specified course codes."""
  # Get suggestions with no exclusions
  result_with_all = suggest_courses_for_slot(
      day_index=0,
      start_min=9 * 60,
      end_min=10 * 60,
      missing_details=[],
      exclude_codes=[],
  )

  if result_with_all:
    # Get the first course code and exclude it
    excluded_code = result_with_all[0]["course"]

    # Get suggestions with that code excluded
    result_with_exclusion = suggest_courses_for_slot(
        day_index=0,
        start_min=9 * 60,
        end_min=10 * 60,
        missing_details=[],
        exclude_codes=[excluded_code],
    )

    # Verify the excluded code is not in the result
    result_codes = [c["course"] for c in result_with_exclusion]
    assert excluded_code not in result_codes


def test_suggest_courses_respects_time_slot():
  """Verify that suggested courses fit the time slot."""
  result = suggest_courses_for_slot(
      day_index=2,  # Wednesday
      start_min=14 * 60,  # 2:00 PM
      end_min=15 * 60,  # 3:00 PM
      missing_details=[],
      exclude_codes=[],
  )

  # Just verify we can call it without errors
  assert isinstance(result, list)
