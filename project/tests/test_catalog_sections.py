"""Catalog section listing, overlap helper, and filter logic."""

from __future__ import annotations

import pytest

from support import schedule_xlsx_available
from utils.scu_course_schedule_xlsx import (
    catalog_facets,
    filter_catalog_sections,
    list_offered_sections,
    section_overlaps_slot,
    section_overlaps_time_bucket,
)


class TestSectionOverlapsSlot:
    def test_class_ending_during_clicked_slot(self):
        section = {
            "meeting_days": [0],
            "meeting_start_min": 0,
            "meeting_end_min": 65,
        }
        assert section_overlaps_slot(section, day_index=0, start_min=60, end_min=90)

    def test_class_before_slot_no_match(self):
        section = {
            "meeting_days": [0],
            "meeting_start_min": 0,
            "meeting_end_min": 30,
        }
        assert not section_overlaps_slot(section, day_index=0, start_min=60, end_min=90)

    def test_wrong_day(self):
        section = {
            "meeting_days": [1],
            "meeting_start_min": 60,
            "meeting_end_min": 90,
        }
        assert not section_overlaps_slot(section, day_index=0, start_min=60, end_min=90)

    def test_missing_times(self):
        assert not section_overlaps_slot(
            {"meeting_days": [0], "meeting_start_min": None, "meeting_end_min": None},
            day_index=0,
            start_min=0,
            end_min=30,
        )


class TestSectionOverlapsTimeBucket:
    def test_morning_class(self):
        section = {"meeting_start_min": 15, "meeting_end_min": 75}
        assert section_overlaps_time_bucket(section, "morning")
        assert not section_overlaps_time_bucket(section, "evening")


@pytest.mark.skipif(not schedule_xlsx_available(), reason="requires schedule xlsx")
class TestListOfferedSectionsIntegration:
    def test_returns_multiple_sections_per_course(self):
        sections = list_offered_sections()
        assert len(sections) > 500
        codes = [s["course"] for s in sections]
        assert codes.count("CSEN 174") >= 1 or any("174" in c for c in codes if "CSEN" in c)

    def test_sections_have_tags_when_present(self):
        sections = list_offered_sections()
        with_tags = [s for s in sections if s.get("course_tags")]
        assert len(with_tags) > 100

    def test_filter_by_tag_rtc(self):
        all_secs = list_offered_sections()
        filtered = filter_catalog_sections(all_secs, tags=["RTC 3"])
        assert len(filtered) > 0
        for s in filtered:
            norms = {t.lower() for t in s.get("course_tags") or []}
            assert "rtc 3" in norms or any("rtc 3" in t for t in norms)

    def test_filter_slot_overlap(self):
        all_secs = list_offered_sections()
        filtered = filter_catalog_sections(
            all_secs,
            day_index=0,
            start_min=60,
            end_min=90,
        )
        for s in filtered:
            assert section_overlaps_slot(
                s, day_index=0, start_min=60, end_min=90
            )

    def test_facets_include_subjects(self):
        sections = list_offered_sections()
        facets = catalog_facets(sections)
        assert len(facets.get("subjects") or []) > 10
        assert len(facets.get("tags") or {}) > 0
