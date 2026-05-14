"""Title overrides and time-conflict detection for the planning agent.

Two bugs surfaced when the LLM scheduled CSEN 122 and ECEN 153 in the
same plan:

  1. CSEN 122L's title came back as "Data Structures and Algorithms Lab"
     instead of "Computer Architecture Laboratory" — the LLM
     hallucinated the title and the agent passed it straight through.

  2. CSEN 122 (M/W/F 9:15-10:20) and ECEN 153 (M/W/F 9:15-10:20) were
     both accepted by the validation step even though they occupy the
     exact same calendar slot.  The frontend then silently rendered only
     one of them, making it look like the lab was orphaned.

These tests pin the corrected behaviour:

  - ``load_course_titles_index`` / ``course_title_for`` resolve the
    authoritative course name from the schedule xlsx, with CSEN↔COEN
    and ECEN↔ELEN aliasing.
  - ``detect_time_conflicts`` returns overlapping pairs.
  - ``_partition_recommended`` rejects the second course in a
    time-conflicting pair with a ``time_conflict_with_<code>`` reason.
  - ``run_planning_agent`` overrides per-course titles after the LLM
    response.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from agents import planning_agent
from utils.scu_course_schedule_xlsx import (
    course_title_for,
    detect_time_conflicts,
)


# ── detect_time_conflicts ────────────────────────────────────────────────────


def _slot(days, start, end, instructors=()):
    return {
        "instructors": list(instructors),
        "meeting_days": list(days),
        "meeting_start_min": start,
        "meeting_end_min": end,
    }


def test_detect_conflict_same_slot_same_days():
    """CSEN 122 and ECEN 153 share M/W/F 9:15-10:20 — must collide."""
    sched = {
        ("CSEN", "122"): _slot([0, 2, 4], 75, 140),
        ("ECEN", "153"): _slot([0, 2, 4], 75, 140),
    }
    conflicts = detect_time_conflicts(["CSEN 122", "ECEN 153"], sched)
    assert conflicts == [(0, 1)]


def test_no_conflict_when_days_disjoint():
    """T/Th 8:30-10:10 does not collide with M/W/F 9:15-10:20."""
    sched = {
        ("ENGL", "181"): _slot([1, 3], 30, 130),
        ("CSEN", "122"): _slot([0, 2, 4], 75, 140),
    }
    assert detect_time_conflicts(["ENGL 181", "CSEN 122"], sched) == []


def test_no_conflict_when_times_disjoint_same_day():
    sched = {
        ("CSEN", "122"): _slot([0], 75, 140),    # 9:15-10:20 Mon
        ("CSEN", "122L"): _slot([0], 375, 540),  # 2:15-5:00 Mon
    }
    assert detect_time_conflicts(["CSEN 122", "CSEN 122L"], sched) == []


def test_conflict_partial_day_overlap():
    """Even one shared weekday + overlapping window counts."""
    sched = {
        ("AAA", "1"): _slot([0, 2], 100, 200),  # Mon/Wed
        ("BBB", "2"): _slot([2, 4], 150, 250),  # Wed/Fri — shares Wed, 150-200 overlap
    }
    assert detect_time_conflicts(["AAA 1", "BBB 2"], sched) == [(0, 1)]


def test_unknown_course_never_conflicts():
    sched = {("CSEN", "122"): _slot([0, 2, 4], 75, 140)}
    # "XYZ 9000" is not in the schedule → cannot conflict
    assert detect_time_conflicts(["CSEN 122", "XYZ 9000"], sched) == []


def test_courses_without_posted_time_skip_conflict():
    sched = {
        ("CSEN", "122"): _slot([0, 2, 4], 75, 140),
        ("CSEN", "194"): _slot([], None, None),  # time TBA
    }
    assert detect_time_conflicts(["CSEN 122", "CSEN 194"], sched) == []


# ── course_title_for (load_course_titles_index aliasing) ─────────────────────


def test_course_title_lookup_with_alias():
    """A title indexed under CSEN should resolve when looking up COEN."""
    titles = {
        ("CSEN", "122"): "Computer Architecture",
        ("CSEN", "122L"): "Computer Architecture Laboratory",
        ("COEN", "122"): "Computer Architecture",    # mirrored
        ("COEN", "122L"): "Computer Architecture Laboratory",
    }
    assert course_title_for("CSEN 122", titles) == "Computer Architecture"
    assert course_title_for("COEN 122", titles) == "Computer Architecture"
    assert course_title_for("CSEN 122L", titles) == "Computer Architecture Laboratory"


def test_course_title_returns_none_for_unknown_code():
    titles = {("CSEN", "122"): "Computer Architecture"}
    assert course_title_for("MATH 99", titles) is None


def test_course_title_real_xlsx_has_correct_csen_122_title():
    """End-to-end against the checked-in schedule xlsx — guards against
    regression on the original bug where the LLM mislabelled CSEN 122L."""
    from utils.scu_course_schedule_xlsx import load_course_titles_index

    idx = load_course_titles_index()
    assert idx, "schedule xlsx not found in test environment"
    assert course_title_for("CSEN 122", idx) == "Computer Architecture"
    assert course_title_for("CSEN 122L", idx) == "Computer Architecture Laboratory"
    # CSEN 12 must NOT bleed into CSEN 122 title (root cause of the regression)
    csen_12 = course_title_for("CSEN 12", idx)
    assert csen_12 != "Computer Architecture"
    assert "Data Structures" in (csen_12 or "")


# ── _partition_recommended time-conflict rejection ──────────────────────────


def test_partition_rejects_time_conflicting_second_course():
    """When two LLM recommendations occupy the same slot, the second is
    rejected with a ``time_conflict_with_<code>`` reason so the feedback
    loop can ask for a replacement."""
    sched = {
        ("CSEN", "122"): _slot([0, 2, 4], 75, 140),
        ("ECEN", "153"): _slot([0, 2, 4], 75, 140),
    }
    recommended = [
        {"course": "CSEN 122", "category": "Major", "units": 4},
        {"course": "ECEN 153", "category": "Major", "units": 4},
    ]
    valid, rejected = planning_agent._partition_recommended(
        recommended, sched, required_codes=None
    )
    assert [v["course"] for v in valid] == ["CSEN 122"]
    assert len(rejected) == 1
    assert rejected[0]["course"] == "ECEN 153"
    assert rejected[0]["_rejection_reason"].startswith("time_conflict_with_")
    assert "CSEN 122" in rejected[0]["_rejection_reason"]


def test_partition_allows_lecture_and_its_lab_different_times():
    """The lecture/lab pair for the SAME course is on disjoint times and
    must both pass partition."""
    sched = {
        ("CSEN", "122"): _slot([0, 2, 4], 75, 140),   # M/W/F 9:15-10:20
        ("CSEN", "122L"): _slot([2], 375, 540),       # Wed 2:15-5:00
    }
    recommended = [
        {"course": "CSEN 122", "category": "Major", "units": 4},
        {"course": "CSEN 122L", "category": "Major", "units": 1},
    ]
    valid, rejected = planning_agent._partition_recommended(
        recommended, sched, required_codes=None
    )
    assert {v["course"] for v in valid} == {"CSEN 122", "CSEN 122L"}
    assert rejected == []


# ── run_planning_agent title override ────────────────────────────────────────


def _stub_client(reply: dict):
    class _Models:
        def generate_content(self, model, contents, config):  # noqa: D401
            return SimpleNamespace(text=json.dumps(reply))

    class _Client:
        models = _Models()

    return _Client()


def test_run_planning_agent_overrides_hallucinated_title(monkeypatch):
    """If the LLM emits CSEN 122L with a wrong title, the agent must
    replace it with the schedule xlsx title."""
    reply = {
        "recommended": [
            {
                "course": "CSEN 122",
                "title": "Some Wrong Name",
                "category": "Major",
                "units": 4,
                "reason": "core",
            },
            {
                "course": "CSEN 122L",
                "title": "Data Structures and Algorithms Lab",  # ← the bug
                "category": "Major",
                "units": 1,
                "reason": "co-req",
            },
        ],
        "total_units": 5,
        "advice": "ok",
        "assistant_reply": "all set.",
    }
    fake_sched = {
        ("CSEN", "122"): _slot([0], None, None),  # in-schedule but TBA
        ("CSEN", "122L"): _slot([0], None, None),
        ("COEN", "122"): _slot([0], None, None),
        ("COEN", "122L"): _slot([0], None, None),
    }
    fake_titles = {
        ("CSEN", "122"): "Computer Architecture",
        ("CSEN", "122L"): "Computer Architecture Laboratory",
        ("COEN", "122"): "Computer Architecture",
        ("COEN", "122L"): "Computer Architecture Laboratory",
    }
    monkeypatch.setattr(planning_agent, "get_genai_client", lambda **_kw: _stub_client(reply))
    monkeypatch.setattr(planning_agent, "load_schedule_section_index", lambda: fake_sched)
    monkeypatch.setattr(planning_agent, "load_category_course_index", lambda: {})
    monkeypatch.setattr(planning_agent, "load_course_titles_index", lambda: fake_titles)

    out = planning_agent.run_planning_agent(
        missing_details=[
            {"course": "CSEN 122", "category": "Major", "units": 4},
            {"course": "CSEN 122L", "category": "Major", "units": 1},
        ],
        user_preference="just architecture",
    )

    by_code = {item["course"]: item for item in out["recommended"]}
    assert by_code["CSEN 122"]["title"] == "Computer Architecture"
    assert by_code["CSEN 122L"]["title"] == "Computer Architecture Laboratory"


def test_run_planning_agent_keeps_llm_title_when_schedule_has_none(monkeypatch):
    """If the schedule xlsx has no entry for a course, keep whatever the
    LLM produced — don't blank it out."""
    reply = {
        "recommended": [
            {
                "course": "PHIL 11",
                "title": "Ethics",
                "category": "Core",
                "units": 4,
                "reason": "core",
            },
        ],
        "total_units": 4,
        "advice": "ok",
        "assistant_reply": "done.",
    }
    monkeypatch.setattr(planning_agent, "get_genai_client", lambda **_kw: _stub_client(reply))
    monkeypatch.setattr(
        planning_agent, "load_schedule_section_index",
        lambda: {("PHIL", "11"): _slot([0], None, None)},
    )
    monkeypatch.setattr(planning_agent, "load_category_course_index", lambda: {})
    # Title index has no PHIL 11 entry
    monkeypatch.setattr(planning_agent, "load_course_titles_index", lambda: {})

    out = planning_agent.run_planning_agent(
        missing_details=[{"course": "PHIL 11", "category": "Core", "units": 4}],
        user_preference="any",
    )
    assert out["recommended"][0]["title"] == "Ethics"
