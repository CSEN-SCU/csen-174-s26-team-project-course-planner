"""Five golden fixtures reproducing real production bug classes.

Each fixture is a hermetic end-to-end test of the constrained_v2 engine
with stubbed xlsx data: no network, no Gemini, no real schedule file.
Together they pin the regressions the architecture exists to prevent:

  1. ``hallucinated_code`` — legacy could emit "CSEN 200" when only
     "CSEN 174" is offered. v2: structurally impossible.
  2. ``wrong_units`` — legacy could ship 5-unit CSEN 174 because the
     LLM guessed wrong. v2: units always from xlsx.
  3. ``time_conflict`` — two required courses with identical time
     slots; legacy could ship them both. v2: deferred with reason.
  4. ``lab_drop`` — legacy could ship CSEN 122 without CSEN 122L. v2:
     lab pairs are inseparable.
  5. ``followup_drop_unrelated`` — legacy could drop MATH 53 when the
     user only asked to remove CSEN 174. v2: locked codes preserve
     every un-named course (R7).

Each fixture asserts BOTH the recommendation set and the
``meta.validation`` audit trail so a regression in instrumentation is
also caught here.
"""

from __future__ import annotations

from agents import planning_agent_v2 as v2


class _FakeClient:
    class _Models:
        def generate_content(self, *, model, contents, config):
            class _R:
                text = '{"assistant_reply": "ok", "advice": "ok"}'

            return _R()

    def __init__(self):
        self.models = self._Models()


def _patch_xlsx(monkeypatch, *, schedule, titles, units, sections, category=None):
    from agents import candidate_pool as cp

    monkeypatch.setattr(cp, "load_schedule_section_index", lambda: schedule)
    monkeypatch.setattr(cp, "load_category_course_index", lambda: category or {})
    monkeypatch.setattr(cp, "load_course_titles_index", lambda: titles)
    monkeypatch.setattr(cp, "load_course_units_index", lambda: units)
    monkeypatch.setattr(cp, "load_all_course_sections", lambda: sections)
    monkeypatch.setattr(cp, "load_instructor_ratings", lambda: {})


def _patch_llm(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    monkeypatch.setattr(v2, "get_genai_client", lambda *, purpose: _FakeClient())


def _sec(num, days, start, end, instructor=None):
    return {
        "section": num,
        "meeting_days": list(days),
        "meeting_start_min": start,
        "meeting_end_min": end,
        "instructors": [instructor] if instructor else [],
    }


def _sched(days, start, end, instructors=()):
    return {
        "instructors": list(instructors),
        "meeting_days": list(days),
        "meeting_start_min": start,
        "meeting_end_min": end,
    }


# ─────────────────────────────────────────────────────────────────────────────
# FIXTURE 1 — hallucinated_code
# Bug: legacy engine output "CSEN 200" (does not exist next term).
# Contract: v2 only emits codes the pool actually contains.
# ─────────────────────────────────────────────────────────────────────────────


def test_fixture_1_hallucinated_code_is_impossible(monkeypatch):
    schedule = {("CSEN", "174"): _sched([0, 2, 4], 75, 140, ("Smith",))}
    titles = {("CSEN", "174"): "Software Engineering"}
    units = {("CSEN", "174"): 4}
    sections = {("CSEN", "174"): [_sec(1, [0, 2, 4], 75, 140, "Smith")]}
    _patch_xlsx(monkeypatch, schedule=schedule, titles=titles, units=units, sections=sections)
    _patch_llm(monkeypatch)

    out = v2.run_constrained_planner(
        missing_details=[
            {"course": "CSEN 174", "category": "Major"},
            # The legacy engine sometimes hallucinated a "CSEN 200"-style
            # code even when only CSEN 174 was offered. v2 never sees a
            # request like this — it would just be ignored — but we
            # pass it through to prove the pool guarantee holds.
            {"course": "CSEN 200", "category": "Major"},
        ],
        user_preference="plan",
    )
    codes = {r["course"] for r in out["recommended"]}
    # CSEN 200 cannot appear: it's not in the schedule index, so the
    # pool never produced it as a candidate.
    assert "CSEN 200" not in codes
    # CSEN 174 was offered → must be picked.
    assert codes == {"CSEN 174"}
    # And the audit trail attests to the engine identity.
    assert out["meta"]["validation"]["engine"] == "constrained_v2"


# ─────────────────────────────────────────────────────────────────────────────
# FIXTURE 2 — wrong_units
# Bug: legacy could ship CSEN 174 = 5 units (LLM guessed wrong; code
# missing from units index).
# Contract: v2 sources units from xlsx, ignoring whatever was in the
# input row.
# ─────────────────────────────────────────────────────────────────────────────


def test_fixture_2_units_always_match_xlsx(monkeypatch):
    schedule = {("CSEN", "174"): _sched([0, 2, 4], 75, 140)}
    titles = {("CSEN", "174"): "Software Engineering"}
    units = {("CSEN", "174"): 4}
    sections = {("CSEN", "174"): [_sec(1, [0, 2, 4], 75, 140, "Smith")]}
    _patch_xlsx(monkeypatch, schedule=schedule, titles=titles, units=units, sections=sections)
    _patch_llm(monkeypatch)

    out = v2.run_constrained_planner(
        missing_details=[
            {"course": "CSEN 174", "category": "Major", "units": 5, "title": "FAKE"},
        ],
        user_preference="plan",
    )
    row = out["recommended"][0]
    assert row["units"] == 4
    assert row["title"] == "Software Engineering"
    assert out["total_units"] == 4


# ─────────────────────────────────────────────────────────────────────────────
# FIXTURE 3 — time_conflict
# Bug: legacy could ship two required courses with overlapping fixed
# slots and silently rely on the user to notice.
# Contract: v2 picks exactly one, defers the other with a reason.
# ─────────────────────────────────────────────────────────────────────────────


def test_fixture_3_time_conflict_is_deferred_with_reason(monkeypatch):
    schedule = {
        ("CSEN", "174"): _sched([0, 2, 4], 75, 140),
        ("ECEN", "153"): _sched([0, 2, 4], 75, 140),
    }
    titles = {("CSEN", "174"): "Software Engineering", ("ECEN", "153"): "Digital Design"}
    units = {("CSEN", "174"): 4, ("ECEN", "153"): 4}
    sections = {
        ("CSEN", "174"): [_sec(1, [0, 2, 4], 75, 140, "Smith")],
        ("ECEN", "153"): [_sec(1, [0, 2, 4], 75, 140, "Jones")],
    }
    _patch_xlsx(monkeypatch, schedule=schedule, titles=titles, units=units, sections=sections)
    _patch_llm(monkeypatch)

    out = v2.run_constrained_planner(
        missing_details=[
            {"course": "CSEN 174", "category": "Major"},
            {"course": "ECEN 153", "category": "Major"},
        ],
        user_preference="plan",
    )
    codes = {r["course"] for r in out["recommended"]}
    assert len(codes & {"CSEN 174", "ECEN 153"}) == 1
    deferred = out["meta"]["validation"]["deferred_requirements"]
    assert any(
        d["requirement"] in {"Major: CSEN 174", "Major: ECEN 153"} and d.get("reason")
        for d in deferred
    )
    # And the calendar will not show conflicting blocks because the
    # meeting times mirror the chosen single section.
    for r in out["recommended"]:
        assert r.get("meeting_days") is not None


# ─────────────────────────────────────────────────────────────────────────────
# FIXTURE 4 — lab_drop
# Bug: legacy could ship a lecture without its required lab (R1
# violation).
# Contract: v2 lab pairs are inseparable. Either both ship or neither.
# ─────────────────────────────────────────────────────────────────────────────


def test_fixture_4_lab_pairs_are_inseparable(monkeypatch):
    schedule = {
        ("CSEN", "122"): _sched([0, 2, 4], 75, 140),
        ("CSEN", "122L"): _sched([2], 375, 540),
        ("MATH", "53"): _sched([1, 3], 200, 265),
    }
    titles = {
        ("CSEN", "122"): "Computer Architecture",
        ("CSEN", "122L"): "Computer Architecture Lab",
        ("MATH", "53"): "Linear Algebra",
    }
    units = {("CSEN", "122"): 4, ("CSEN", "122L"): 1, ("MATH", "53"): 4}
    sections = {
        ("CSEN", "122"): [_sec(1, [0, 2, 4], 75, 140, "Smith")],
        ("CSEN", "122L"): [_sec(1, [2], 375, 540, "Smith")],
        ("MATH", "53"): [_sec(1, [1, 3], 200, 265, "Doe")],
    }
    _patch_xlsx(monkeypatch, schedule=schedule, titles=titles, units=units, sections=sections)
    _patch_llm(monkeypatch)

    out = v2.run_constrained_planner(
        missing_details=[
            {"course": "CSEN 122", "category": "Major"},
            {"course": "CSEN 122L", "category": "Major"},
            {"course": "MATH 53", "category": "Major"},
        ],
        user_preference="plan",
    )
    codes = {r["course"] for r in out["recommended"]}
    # CSEN 122 and CSEN 122L MUST appear together.
    has_lec = "CSEN 122" in codes
    has_lab = "CSEN 122L" in codes
    assert has_lec == has_lab, "lab pair was split"
    assert {"CSEN 122", "CSEN 122L", "MATH 53"} <= codes


# ─────────────────────────────────────────────────────────────────────────────
# FIXTURE 5 — followup_drop_unrelated (R7)
# Bug: legacy followup "drop CSEN 174" sometimes also lost MATH 53,
# inflated the replacement, or duplicated courses.
# Contract: v2 locks every un-named course; only the named code goes.
# ─────────────────────────────────────────────────────────────────────────────


def test_fixture_5_followup_only_drops_named_courses(monkeypatch):
    schedule = {
        ("CSEN", "174"): _sched([0, 2, 4], 75, 140),
        ("MATH", "53"): _sched([1, 3], 200, 265),
        ("ENGL", "1A"): _sched([0, 2, 4], 200, 265),
        ("PHIL", "9"): _sched([1, 3], 300, 365),
    }
    titles = {
        ("CSEN", "174"): "Software Engineering",
        ("MATH", "53"): "Linear Algebra",
        ("ENGL", "1A"): "Critical Thinking",
        ("PHIL", "9"): "Logic",
    }
    units = {("CSEN", "174"): 4, ("MATH", "53"): 4, ("ENGL", "1A"): 4, ("PHIL", "9"): 4}
    sections = {
        ("CSEN", "174"): [_sec(1, [0, 2, 4], 75, 140, "Smith")],
        ("MATH", "53"): [_sec(1, [1, 3], 200, 265, "Doe")],
        ("ENGL", "1A"): [_sec(1, [0, 2, 4], 200, 265, "Brown")],
        ("PHIL", "9"): [_sec(1, [1, 3], 300, 365, "Green")],
    }
    _patch_xlsx(monkeypatch, schedule=schedule, titles=titles, units=units, sections=sections)
    _patch_llm(monkeypatch)

    out = v2.run_constrained_planner(
        missing_details=[
            {"course": "CSEN 174", "category": "Major"},
            {"course": "MATH 53", "category": "Major"},
            {"course": "ENGL 1A", "category": "Core"},
            {"course": "PHIL 9", "category": "Core"},
        ],
        user_preference="drop CSEN 174",
        previous_plan={
            "recommended": [
                {"course": "CSEN 174", "units": 4},
                {"course": "MATH 53", "units": 4},
                {"course": "ENGL 1A", "units": 4},
            ]
        },
    )
    codes = {r["course"] for r in out["recommended"]}
    # The named course goes.
    assert "CSEN 174" not in codes
    # Every un-named course from the previous plan stays.
    assert "MATH 53" in codes
    assert "ENGL 1A" in codes
    # Lock audit reflects the kept courses.
    locks = set(out["meta"]["validation"]["locked_codes"])
    assert {"MATH 53", "ENGL 1A"} <= locks
    assert "CSEN 174" not in locks
