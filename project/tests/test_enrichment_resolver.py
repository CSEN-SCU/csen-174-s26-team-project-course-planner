"""Tests for department-scoped Educational Enrichment resolution."""

from __future__ import annotations

from utils.enrichment_resolver import (
    course_matches_enrichment_track,
    enrichment_track_label,
    filter_enrichment_codes_for_preference,
    has_educational_enrichment_gap,
    infer_enrichment_subjects,
    is_low_level_chin_course,
    list_enrichment_course_codes,
    resolve_enrichment_subjects_for_slot,
    implicit_removal_codes_for_followup,
    should_show_slot_enrichment,
)


def test_has_enrichment_gap():
    md = [{"requirement": "Educational Enrichment – Courses"}]
    assert has_educational_enrichment_gap(md) is True
    assert has_educational_enrichment_gap([{"requirement": "Core: ENGR: RTC 3"}]) is False


def test_infer_chinese_from_natural_language():
    assert infer_enrichment_subjects("我想加一门中文课满足 enrichment") == ["CHIN"]
    assert infer_enrichment_subjects("我现在是中国人，只能上高阶中文") == ["CHIN"]
    assert enrichment_track_label(["CHIN"]) == "Chinese (CHIN)"


def test_implicit_removal_chin1_for_native_speaker():
    prev = {"recommended": [{"course": "CHIN 1"}, {"course": "THTR 189"}]}
    out = implicit_removal_codes_for_followup("我是中国人只能上高阶中文", prev)
    assert out == {"CHIN 1"}


def test_should_show_slot_enrichment_with_chin_on_plan():
    assert should_show_slot_enrichment(
        "",
        [{"requirement": "RTC 3"}],
        plan_course_codes=["CHIN 1"],
    )


def test_filter_low_level_chin_for_native_speaker():
    codes = ["CHIN 1", "CHIN 125", "CHIN 11A"]
    filtered = filter_enrichment_codes_for_preference(
        codes, "我是中国人只能上高阶中文"
    )
    assert "CHIN 1" not in filtered
    assert "CHIN 11A" not in filtered
    assert "CHIN 125" in filtered
    assert is_low_level_chin_course("CHIN 1")
    assert not is_low_level_chin_course("CHIN 125")


def test_infer_explicit_subject():
    out = infer_enrichment_subjects("add a CHIN course for enrichment")
    assert out == ["CHIN"]


def test_infer_chinese_swap_ignores_removed_course_prefix():
    out = infer_enrichment_subjects("replace ECEN 153 with a Chinese class")
    assert out == ["CHIN"]


def test_course_matches_chin_prefix_or_title():
    assert course_matches_enrichment_track("CHIN 125", "Love in Sino Films", ["CHIN"])
    assert course_matches_enrichment_track(
        "HIST 50", "Modern Chinese History", ["CHIN"]
    )
    assert not course_matches_enrichment_track("ENGL 1", "Composition", ["CHIN"])


def test_list_codes_from_fake_schedule():
    sched = {
        ("CHIN", "1"): {},
        ("CHIN", "125"): {},
        ("ENGL", "1"): {},
    }
    titles = {("CHIN", "125"): "Chinese Cinema"}
    codes = list_enrichment_course_codes(sched, ["CHIN"], titles)
    assert set(codes) == {"CHIN 1", "CHIN 125"}


def test_slot_default_chinese_when_unspecified():
    subjects, label, prompt = resolve_enrichment_subjects_for_slot("")
    assert subjects == ["CHIN"]
    assert label == "Chinese (CHIN)"
    assert prompt is not None
