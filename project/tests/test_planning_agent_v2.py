"""Integration tests for the constrained planner v2.

Stubs the Gemini client and xlsx loaders so the engine runs without
disk or network. Validates:
  - hallucination is structurally impossible (only pool codes appear);
  - canonical titles/units always win, never the LLM;
  - meeting times mirror the solver's chosen section;
  - lab pairs survive the full pipeline (R1);
  - follow-up edits preserve un-named courses (R7);
  - meta.validation carries the engine name + diagnostic fields.
"""

from __future__ import annotations

from agents import planning_agent_v2 as v2


class _FakeClient:
    """Mock the GenAI client. Returns canned JSON prose."""

    class _Models:
        def generate_content(self, *, model, contents, config):
            class _R:
                text = '{"assistant_reply": "Here is your plan.", "advice": "Looks good."}'

            return _R()

    def __init__(self):
        self.models = self._Models()


def _patch_xlsx(monkeypatch, schedule_index, titles, units, all_sections, category_index=None):
    """Stub all xlsx loaders the engine touches."""
    from agents import candidate_pool as cp

    monkeypatch.setattr(cp, "load_schedule_section_index", lambda: schedule_index)
    monkeypatch.setattr(cp, "load_category_course_index", lambda: category_index or {})
    monkeypatch.setattr(cp, "load_course_titles_index", lambda: titles)
    monkeypatch.setattr(cp, "load_course_units_index", lambda: units)
    monkeypatch.setattr(cp, "load_all_course_sections", lambda: all_sections)
    monkeypatch.setattr(cp, "load_instructor_ratings", lambda: {})


def _patch_llm(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(v2, "get_genai_client", lambda *, purpose: _FakeClient())


def _sec(num, days, start, end, instructor=None):
    return {
        "section": num,
        "meeting_days": list(days),
        "meeting_start_min": start,
        "meeting_end_min": end,
        "instructors": [instructor] if instructor else [],
    }


def _sched_entry(days, start, end, instructors=()):
    return {
        "instructors": list(instructors),
        "meeting_days": list(days),
        "meeting_start_min": start,
        "meeting_end_min": end,
    }


# ── core happy path ─────────────────────────────────────────────────────────


def test_v2_engine_returns_only_pool_codes(monkeypatch):
    """The engine must emit only codes that were in the candidate pool;
    hallucination is structurally impossible."""
    _patch_xlsx(
        monkeypatch,
        schedule_index={
            ("CSEN", "174"): _sched_entry([0, 2, 4], 75, 140, ("Smith",)),
            ("MATH", "53"): _sched_entry([1, 3], 200, 290, ("Doe",)),
        },
        titles={
            ("CSEN", "174"): "Software Engineering",
            ("MATH", "53"): "Linear Algebra",
        },
        units={
            ("CSEN", "174"): 4,
            ("MATH", "53"): 4,
        },
        all_sections={
            ("CSEN", "174"): [_sec(1, [0, 2, 4], 75, 140, "Smith")],
            ("MATH", "53"): [_sec(1, [1, 3], 200, 290, "Doe")],
        },
    )
    _patch_llm(monkeypatch)

    out = v2.run_constrained_planner(
        missing_details=[
            {"course": "CSEN 174", "category": "Major"},
            {"course": "MATH 53", "category": "Major"},
        ],
        user_preference="plan my next term",
    )
    codes = {r["course"] for r in out["recommended"]}
    assert codes == {"CSEN 174", "MATH 53"}
    assert out["total_units"] == 8
    assert out["meta"]["validation"]["engine"] == "constrained_v2"
    assert out["meta"]["validation"]["rejected"] == []
    assert out["meta"]["validation"]["repaired"] == []
    assert out["meta"]["validation"]["candidate_count"] == 2


def test_v2_ignores_educational_enrichment(monkeypatch):
    """Educational Enrichment must not add THTR/GNSX/etc. to a v2 plan."""
    _patch_xlsx(
        monkeypatch,
        schedule_index={
            ("CSEN", "174"): _sched_entry([0, 2, 4], 75, 140, ("Smith",)),
            ("THTR", "189"): _sched_entry([1, 3], 200, 290, ("Jones",)),
        },
        titles={
            ("CSEN", "174"): "Software Engineering",
            ("THTR", "189"): "Theatre and Society",
        },
        units={("CSEN", "174"): 4, ("THTR", "189"): 5},
        all_sections={
            ("CSEN", "174"): [_sec(1, [0, 2, 4], 75, 140, "Smith")],
            ("THTR", "189"): [_sec(1, [1, 3], 200, 290, "Jones")],
        },
        category_index={"educational enrichment": ["THTR 189", "GNSX 115"]},
    )
    _patch_llm(monkeypatch)

    out = v2.run_constrained_planner(
        missing_details=[
            {"course": "CSEN 174", "category": "Major"},
            {
                "requirement": (
                    "Computer Science and Engineering Major: "
                    "Educational Enrichment – Courses"
                ),
            },
        ],
        user_preference="plan my next term",
    )
    codes = {r["course"] for r in out["recommended"]}
    assert codes == {"CSEN 174"}
    assert "educational enrichment" not in out["meta"]["validation"]["must_cover"]


def test_v2_titles_and_units_are_canonical(monkeypatch):
    """The engine must use xlsx titles + units, never the input's."""
    _patch_xlsx(
        monkeypatch,
        schedule_index={
            ("CSEN", "174"): _sched_entry([0, 2, 4], 75, 140),
        },
        titles={("CSEN", "174"): "Software Engineering"},
        units={("CSEN", "174"): 4},
        all_sections={("CSEN", "174"): [_sec(1, [0, 2, 4], 75, 140, "Smith")]},
    )
    _patch_llm(monkeypatch)
    out = v2.run_constrained_planner(
        missing_details=[
            {"course": "CSEN 174", "category": "Major", "title": "WRONG TITLE", "units": 99},
        ],
        user_preference="plan",
    )
    row = out["recommended"][0]
    assert row["title"] == "Software Engineering"
    assert row["units"] == 4


def test_v2_mirrors_meeting_times_to_top_level(monkeypatch):
    """The frontend CalendarView reads top-level meeting_days/start/end
    (planCalendar.ts Path B). The engine must mirror its chosen
    section's times there."""
    _patch_xlsx(
        monkeypatch,
        schedule_index={
            ("CSEN", "174"): _sched_entry([0, 2, 4], 75, 140),
        },
        titles={("CSEN", "174"): "Software Engineering"},
        units={("CSEN", "174"): 4},
        all_sections={
            ("CSEN", "174"): [
                _sec(1, [0, 2, 4], 75, 140, "Smith"),
                _sec(2, [1, 3], 200, 265, "Jones"),
            ],
        },
    )
    _patch_llm(monkeypatch)
    out = v2.run_constrained_planner(
        missing_details=[{"course": "CSEN 174", "category": "Major"}],
        user_preference="plan",
    )
    row = out["recommended"][0]
    # Top-level mirror present
    assert "meeting_days" in row
    assert "meeting_start_min" in row
    assert "meeting_end_min" in row
    # And the rich section block
    assert row["section"]["section_number"] in (1, 2)
    assert row["meeting_start_min"] == row["section"]["meeting_start_min"]
    assert row["_chosen_section"] == row["section"]["section_number"]


# ── lab pairing (R1) ─────────────────────────────────────────────────────────


def test_v2_pairs_lab_through_full_engine(monkeypatch):
    _patch_xlsx(
        monkeypatch,
        schedule_index={
            ("CSEN", "122"): _sched_entry([0, 2, 4], 75, 140),
            ("CSEN", "122L"): _sched_entry([2], 375, 540),
        },
        titles={
            ("CSEN", "122"): "Computer Architecture",
            ("CSEN", "122L"): "Computer Architecture Laboratory",
        },
        units={("CSEN", "122"): 4, ("CSEN", "122L"): 1},
        all_sections={
            ("CSEN", "122"): [_sec(1, [0, 2, 4], 75, 140, "Smith")],
            ("CSEN", "122L"): [_sec(1, [2], 375, 540, "Smith")],
        },
    )
    _patch_llm(monkeypatch)
    out = v2.run_constrained_planner(
        missing_details=[
            {"course": "CSEN 122", "category": "Major"},
            {"course": "CSEN 122L", "category": "Major"},
        ],
        user_preference="plan",
    )
    codes = {r["course"] for r in out["recommended"]}
    assert codes == {"CSEN 122", "CSEN 122L"}


# ── follow-up edits (R7) ────────────────────────────────────────────────────


def test_v2_followup_keeps_unnamed_courses(monkeypatch):
    """User says 'drop CSEN 174'; MATH 53 must stay because it was in
    the previous plan and the user didn't name it."""
    _patch_xlsx(
        monkeypatch,
        schedule_index={
            ("CSEN", "174"): _sched_entry([0, 2, 4], 75, 140),
            ("MATH", "53"): _sched_entry([1, 3], 200, 265),
            ("ENGL", "1A"): _sched_entry([0, 2, 4], 200, 265),
        },
        titles={
            ("CSEN", "174"): "Software Engineering",
            ("MATH", "53"): "Linear Algebra",
            ("ENGL", "1A"): "Critical Thinking & Writing",
        },
        units={("CSEN", "174"): 4, ("MATH", "53"): 4, ("ENGL", "1A"): 4},
        all_sections={
            ("CSEN", "174"): [_sec(1, [0, 2, 4], 75, 140, "Smith")],
            ("MATH", "53"): [_sec(1, [1, 3], 200, 265, "Doe")],
            ("ENGL", "1A"): [_sec(1, [0, 2, 4], 200, 265, "Brown")],
        },
    )
    _patch_llm(monkeypatch)
    out = v2.run_constrained_planner(
        missing_details=[
            {"course": "CSEN 174", "category": "Major"},
            {"course": "MATH 53", "category": "Major"},
            {"course": "ENGL 1A", "category": "Core"},
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
    # MATH 53 and ENGL 1A must stay (user did not name them for removal).
    assert "MATH 53" in codes
    assert "ENGL 1A" in codes
    # CSEN 174 was named for removal — should be gone.
    assert "CSEN 174" not in codes
    # The locked-codes audit trail surfaces the kept courses.
    locks = set(out["meta"]["validation"]["locked_codes"])
    assert "MATH 53" in locks
    assert "ENGL 1A" in locks
    assert "CSEN 174" not in locks


# ── deferred requirements ───────────────────────────────────────────────────


def test_v2_records_deferred_when_constraints_make_plan_infeasible(monkeypatch):
    """Two required courses with identical fixed time slots → one must
    be deferred; the engine reports it explicitly, never silently."""
    _patch_xlsx(
        monkeypatch,
        schedule_index={
            ("CSEN", "174"): _sched_entry([0, 2, 4], 75, 140),
            ("ECEN", "153"): _sched_entry([0, 2, 4], 75, 140),
        },
        titles={
            ("CSEN", "174"): "Software Engineering",
            ("ECEN", "153"): "Digital Design",
        },
        units={("CSEN", "174"): 4, ("ECEN", "153"): 4},
        all_sections={
            ("CSEN", "174"): [_sec(1, [0, 2, 4], 75, 140, "Smith")],
            ("ECEN", "153"): [_sec(1, [0, 2, 4], 75, 140, "Jones")],
        },
    )
    _patch_llm(monkeypatch)
    out = v2.run_constrained_planner(
        missing_details=[
            {"course": "CSEN 174", "category": "Major"},
            {"course": "ECEN 153", "category": "Major"},
        ],
        user_preference="plan",
    )
    codes = {r["course"] for r in out["recommended"]}
    # Exactly one of the two can be picked; the other is deferred.
    assert len(codes & {"CSEN 174", "ECEN 153"}) == 1
    deferred_labels = {d["requirement"] for d in out["meta"]["validation"]["deferred_requirements"]}
    assert deferred_labels & {"Major: CSEN 174", "Major: ECEN 153"}


# ── completed-course filtering ──────────────────────────────────────────────


def test_v2_excludes_completed_courses(monkeypatch):
    _patch_xlsx(
        monkeypatch,
        schedule_index={
            ("CSEN", "174"): _sched_entry([0, 2, 4], 75, 140),
            ("MATH", "53"): _sched_entry([1, 3], 200, 265),
        },
        titles={("CSEN", "174"): "Software Engineering", ("MATH", "53"): "Linear Algebra"},
        units={("CSEN", "174"): 4, ("MATH", "53"): 4},
        all_sections={
            ("CSEN", "174"): [_sec(1, [0, 2, 4], 75, 140, "Smith")],
            ("MATH", "53"): [_sec(1, [1, 3], 200, 265, "Doe")],
        },
    )
    _patch_llm(monkeypatch)
    out = v2.run_constrained_planner(
        missing_details=[
            {"course": "CSEN 174", "category": "Major"},
            {"course": "MATH 53", "category": "Major"},
        ],
        user_preference="plan",
        completed_course_codes=["MATH 53"],
    )
    codes = {r["course"] for r in out["recommended"]}
    assert "MATH 53" not in codes
    assert "CSEN 174" in codes
