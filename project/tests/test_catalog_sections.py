"""Catalog section listing, overlap helper, and filter logic."""

from __future__ import annotations

import pytest

from support import schedule_xlsx_available
from utils.scu_course_schedule_xlsx import (
    catalog_facets,
    catalog_time_windows,
    enrich_section_instructor_rating,
    filter_catalog_sections,
    list_offered_sections,
    section_matches_time_window,
    section_overlaps_slot,
    section_overlaps_time_window,
    sort_catalog_sections,
)


class TestCatalogSortAndRatings:
    def test_sort_by_rating_desc_nulls_last(self):
        rows = [
            {"subject": "CSEN", "course": "A", "section": 1, "instructor_rating": 3.0},
            {"subject": "CSEN", "course": "B", "section": 1, "instructor_rating": 4.5},
            {"subject": "CSEN", "course": "C", "section": 1, "instructor_rating": None},
        ]
        out = sort_catalog_sections(rows, "rating")
        assert [r["course"] for r in out] == ["B", "A", "C"]

    def test_sort_by_difficulty_asc_nulls_last(self):
        rows = [
            {"subject": "CSEN", "course": "Hard", "section": 1, "instructor_difficulty": 4.5},
            {"subject": "CSEN", "course": "Easy", "section": 1, "instructor_difficulty": 2.0},
            {"subject": "CSEN", "course": "Unknown", "section": 1, "instructor_difficulty": None},
        ]
        out = sort_catalog_sections(rows, "difficulty")
        assert [r["course"] for r in out] == ["Easy", "Hard", "Unknown"]

    def test_sort_by_balanced(self):
        rows = [
            {
                "subject": "CSEN",
                "course": "Low",
                "section": 1,
                "instructor_balanced_score": 0.3,
            },
            {
                "subject": "CSEN",
                "course": "High",
                "section": 1,
                "instructor_balanced_score": 0.9,
            },
        ]
        out = sort_catalog_sections(rows, "balanced")
        assert out[0]["course"] == "High"

    def test_enrich_adds_rating_fields(self):
        ratings = {
            "jane doe": {
                "instructor": "Jane Doe",
                "rating": 4.2,
                "difficulty": 3.1,
                "would_take_again_pct": 82.0,
                "source": "rmp",
            }
        }
        section = {
            "course": "CSEN 999",
            "section": 1,
            "instructors": ["Jane Doe"],
        }
        out = enrich_section_instructor_rating(section, ratings)
        assert out["instructor_rating"] == 4.2
        assert out["instructor_difficulty"] == 3.1
        assert out["instructor_balanced_score"] is not None


class TestTagFilterMatchMode:
    def test_tags_or_matches_any(self):
        sections = [
            {"course": "A", "course_tags": ["RTC 3", "ELSJ"]},
            {"course": "B", "course_tags": ["RTC 3"]},
            {"course": "C", "course_tags": ["ELSJ"]},
        ]
        out = filter_catalog_sections(
            sections, tags=["RTC 3", "ELSJ"], tags_match="or"
        )
        assert {s["course"] for s in out} == {"A", "B", "C"}

    def test_tags_and_requires_all(self):
        sections = [
            {"course": "A", "course_tags": ["RTC 3", "ELSJ"]},
            {"course": "B", "course_tags": ["RTC 3"]},
            {"course": "C", "course_tags": ["ELSJ"]},
        ]
        out = filter_catalog_sections(
            sections, tags=["RTC 3", "ELSJ"], tags_match="and"
        )
        assert [s["course"] for s in out] == ["A"]


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


class TestTimeWindowFilter:
    def test_two_hour_window_overlap(self):
        # 9:15–10:20 AM → overlaps 8:00–10:00 window (65 min of overlap at end of window)
        section = {"meeting_start_min": 75, "meeting_end_min": 140}
        assert section_overlaps_time_window(section, 0, 120)
        assert section_matches_time_window(section, "0:120")

    def test_three_hour_lab_spans_windows(self):
        # 1:00–4:00 PM lab (300–480) overlaps 12–2 and 2–4 with ≥30 min each
        lab = {"meeting_start_min": 300, "meeting_end_min": 480}
        assert section_overlaps_time_window(lab, 240, 360)
        assert section_overlaps_time_window(lab, 360, 480)

    def test_no_overlap_if_less_than_30_min(self):
        section = {"meeting_start_min": 115, "meeting_end_min": 125}
        assert not section_overlaps_time_window(section, 0, 120, min_overlap_min=30)


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
        assert len(facets.get("meeting_times") or []) == 7

    def test_filter_by_time_window(self):
        all_secs = list_offered_sections()
        windows = catalog_time_windows()
        assert len(windows) >= 4
        wid = windows[0]["id"]
        filtered = filter_catalog_sections(all_secs, meeting_time_slots=[wid])
        assert filtered
        for s in filtered:
            assert section_matches_time_window(s, wid)
