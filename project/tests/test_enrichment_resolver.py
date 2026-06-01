"""Tests for department-scoped Educational Enrichment resolution."""

from __future__ import annotations

from utils.enrichment_resolver import (
    course_matches_enrichment_track,
    enrichment_track_label,
    has_educational_enrichment_gap,
    infer_enrichment_subjects,
    list_enrichment_course_codes,
    resolve_enrichment_subjects_for_slot,
    should_show_slot_enrichment,
)


def test_has_enrichment_gap():
    md = [{"requirement": "Educational Enrichment – Courses"}]
    assert has_educational_enrichment_gap(md) is True
    assert has_educational_enrichment_gap([{"requirement": "Core: ENGR: RTC 3"}]) is False


def test_infer_subjects_not_from_chinese_natural_language():
    assert infer_enrichment_subjects("我想加一门中文课满足 enrichment") == []
    assert infer_enrichment_subjects("我现在是中国人，只能上高阶中文") == []


def test_should_show_slot_enrichment_with_named_track_on_plan():
    assert should_show_slot_enrichment(
        "HIST enrichment",
        [{"requirement": "RTC 3"}],
        plan_course_codes=["HIST 50"],
    )


def test_infer_explicit_subject():
    out = infer_enrichment_subjects("add a HIST course for enrichment")
    assert "HIST" in out
    assert "CHIN" not in infer_enrichment_subjects("add a CHIN course for enrichment")


def test_course_matches_department_prefix_only():
    assert course_matches_enrichment_track("HIST 50", "Modern History", ["HIST"])
    assert not course_matches_enrichment_track(
        "HIST 50", "Modern Chinese History", ["ARTS"]
    )
    assert not course_matches_enrichment_track("ENGL 1", "Composition", ["HIST"])


def test_list_codes_from_fake_schedule():
    sched = {
        ("HIST", "1"): {},
        ("HIST", "50"): {},
        ("ENGL", "1"): {},
    }
    titles = {("HIST", "50"): "Modern History"}
    codes = list_enrichment_course_codes(sched, ["HIST"], titles)
    assert set(codes) == {"HIST 1", "HIST 50"}


def test_slot_no_default_when_unspecified():
    subjects, label, prompt = resolve_enrichment_subjects_for_slot("")
    assert subjects == []
    assert label == ""
    assert prompt is not None
    assert "Chinese" not in prompt


def test_enrichment_track_label():
    assert enrichment_track_label(["HIST"]) == "HIST"
    assert enrichment_track_label(["HIST", "ARTS"]) == "HIST / ARTS"
