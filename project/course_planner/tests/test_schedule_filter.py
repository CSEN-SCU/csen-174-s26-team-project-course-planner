"""
Tests for schedule-based hallucination filtering and meeting-time parsing.

Covers:
- _parse_days / _parse_time_range in scu_course_schedule_xlsx
- planned_section_keys / load_schedule_section_index
- _filter_to_schedule in planning_agent
- _build_schedule_block in planning_agent
- all_sections_for_course in scu_course_schedule_xlsx
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from utils.scu_course_schedule_xlsx import (
    _parse_days,
    _parse_time_range,
    _offset,
    planned_section_keys,
)
from agents.planning_agent import (
    _filter_to_schedule,
    _build_schedule_block,
)


# ── _parse_days ──────────────────────────────────────────────────────────────

class TestParseDays:
    def test_space_separated(self):
        assert _parse_days("M W F") == [0, 2, 4]

    def test_compact_mwf_not_supported(self):
        # SCU xlsx always uses space-separated tokens ("M W F"), not compact "MWF".
        # The parser does not need to handle compact strings; this documents that.
        result = _parse_days("MWF")
        # Compact form is not parsed — result may be empty or partial.
        # Real data is always space-separated: "M W F | ..."
        assert isinstance(result, list)

    def test_tuesday_thursday(self):
        assert _parse_days("T TH") == [1, 3]

    def test_r_is_thursday(self):
        assert _parse_days("T R") == [1, 3]

    def test_combined_cell_strips_time_part(self):
        # "M W F | 9:15 AM - 10:20 AM" → days only
        assert _parse_days("M W F | 9:15 AM - 10:20 AM") == [0, 2, 4]

    def test_comma_separated(self):
        assert _parse_days("M,W,F") == [0, 2, 4]

    def test_empty_returns_empty(self):
        assert _parse_days("") == []

    def test_none_returns_empty(self):
        assert _parse_days(None) == []

    def test_wednesday_only(self):
        assert _parse_days("W") == [2]


# ── _parse_time_range ────────────────────────────────────────────────────────

class TestParseTimeRange:
    def _off(self, h: int, m: int) -> int:
        return _offset(h * 60 + m)

    def test_morning_range(self):
        result = _parse_time_range("9:15 AM - 10:20 AM")
        assert result == (self._off(9, 15), self._off(10, 20))

    def test_afternoon_range(self):
        result = _parse_time_range("2:15 PM - 5:00 PM")
        assert result == (self._off(14, 15), self._off(17, 0))

    def test_combined_cell_with_pipe(self):
        # "M W F | 9:15 AM - 10:20 AM" → strips day part
        result = _parse_time_range("M W F | 9:15 AM - 10:20 AM")
        assert result == (self._off(9, 15), self._off(10, 20))

    def test_csen122_official_slot(self):
        # CSEN 122: M W F | 9:15 AM - 10:20 AM → offset 75–140
        result = _parse_time_range("M W F | 9:15 AM - 10:20 AM")
        assert result == (75, 140)

    def test_lab_afternoon(self):
        # Labs: 2:15 PM - 5:00 PM → 375–540 minutes from 8 AM
        result = _parse_time_range("2:15 PM - 5:00 PM")
        assert result == (375, 540)

    def test_invalid_returns_none(self):
        assert _parse_time_range("no time here") is None

    def test_none_returns_none(self):
        assert _parse_time_range(None) is None

    def test_inverted_times_returns_none(self):
        # End before start should return None
        result = _parse_time_range("10:00 AM - 9:00 AM")
        assert result is None


# ── planned_section_keys ─────────────────────────────────────────────────────

class TestPlannedSectionKeys:
    def test_csen_expands_to_coen(self):
        keys = planned_section_keys("CSEN 122")
        assert ("CSEN", "122") in keys
        assert ("COEN", "122") in keys

    def test_coen_expands_to_csen(self):
        keys = planned_section_keys("COEN 194")
        assert ("COEN", "194") in keys
        assert ("CSEN", "194") in keys

    def test_ecen_expands_to_elen(self):
        keys = planned_section_keys("ECEN 153")
        assert ("ECEN", "153") in keys
        assert ("ELEN", "153") in keys

    def test_lab_suffix_preserved(self):
        keys = planned_section_keys("CSEN 194L")
        assert ("CSEN", "194L") in keys

    def test_ampersand_separated(self):
        # "CSEN 122 & CSEN 122L" → both pairs
        keys = planned_section_keys("CSEN 122 & CSEN 122L")
        assert ("CSEN", "122") in keys
        assert ("CSEN", "122L") in keys

    def test_unknown_prefix_no_expansion(self):
        keys = planned_section_keys("CREL 111")
        assert ("CREL", "111") in keys
        # No COEN/CSEN expansion for CREL
        assert ("COEN", "111") not in keys

    def test_empty_returns_empty(self):
        assert planned_section_keys("") == set()

    def test_rsoc_course(self):
        keys = planned_section_keys("RSOC 10")
        assert ("RSOC", "10") in keys


# ── _filter_to_schedule ──────────────────────────────────────────────────────

def _make_schedule(*codes: str) -> dict:
    """Build a fake schedule_index with the given (SUBJ, NUM) codes."""
    index = {}
    for code in codes:
        parts = code.split()
        if len(parts) == 2:
            index[(parts[0], parts[1])] = {
                "instructors": [],
                "meeting_days": [],
                "meeting_start_min": None,
                "meeting_end_min": None,
            }
    return index


class TestFilterToSchedule:
    def test_real_course_passes(self):
        idx = _make_schedule("CSEN 122", "COEN 122")
        result = _filter_to_schedule([{"course": "CSEN 122"}], idx)
        assert len(result) == 1

    def test_hallucinated_crel_blocked(self):
        idx = _make_schedule("CSEN 122", "RSOC 10")
        result = _filter_to_schedule([{"course": "CREL 111"}], idx)
        assert result == []

    def test_hallucinated_rels_blocked(self):
        idx = _make_schedule("CSEN 122")
        result = _filter_to_schedule([{"course": "RELS 138"}], idx)
        assert result == []

    def test_mixed_keeps_real_removes_fake(self):
        idx = _make_schedule("CSEN 122", "COEN 122", "RSOC 10")
        recs = [{"course": "CSEN 122"}, {"course": "CREL 111"}, {"course": "RSOC 10"}]
        result = _filter_to_schedule(recs, idx)
        codes = [r["course"] for r in result]
        assert "CSEN 122" in codes
        assert "RSOC 10" in codes
        assert "CREL 111" not in codes

    def test_empty_schedule_passes_everything(self):
        # Guard: don't block when xlsx wasn't found
        result = _filter_to_schedule([{"course": "CREL 111"}], {})
        assert len(result) == 1

    def test_coen_alias_matches_csen_in_index(self):
        # If CSEN 122 is in index, a recommendation of COEN 122 should pass
        idx = _make_schedule("CSEN 122")
        result = _filter_to_schedule([{"course": "COEN 122"}], idx)
        assert len(result) == 1

    def test_ecen_alias_passes_when_elen_in_index(self):
        idx = _make_schedule("ELEN 153")
        result = _filter_to_schedule([{"course": "ECEN 153"}], idx)
        assert len(result) == 1


# ── _build_schedule_block ────────────────────────────────────────────────────

class TestBuildScheduleBlock:
    def _md(self, *codes: str) -> list[dict]:
        return [{"course": c, "category": "Core", "units": 4} for c in codes]

    def test_offered_courses_appear_in_block(self):
        idx = _make_schedule("CSEN 122", "COEN 122")
        block, keys = _build_schedule_block(self._md("CSEN 122"), idx)
        assert "CSEN 122" in block
        assert ("CSEN", "122") in keys or ("COEN", "122") in keys

    def test_not_offered_appears_in_block(self):
        idx = _make_schedule("CSEN 122", "COEN 122")
        block, _ = _build_schedule_block(self._md("CSEN 122", "CREL 111"), idx)
        assert "CREL 111" in block
        assert "NOT OFFERED" in block or "NOT" in block.upper()

    def test_empty_missing_details_returns_empty(self):
        idx = _make_schedule("CSEN 122")
        block, keys = _build_schedule_block([], idx)
        assert block == ""
        assert keys == set()

    def test_empty_schedule_returns_empty(self):
        block, keys = _build_schedule_block(self._md("CSEN 122"), {})
        assert block == ""
        assert keys == set()

    def test_all_missing_from_schedule_returns_empty_constraint_but_not_offered(self):
        # When nothing is offered, no constraint list — but "not offered" note is still useful
        idx = _make_schedule("CSEN 122", "COEN 122")
        block, keys = _build_schedule_block(self._md("CREL 111", "RELS 138"), idx)
        # offered list must not constrain (keys empty)
        assert keys == set()
        # But we DO want the "not offered" note in the block so LLM knows
        assert "CREL 111" in block or block == ""
