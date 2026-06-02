"""Deterministic unit-cap enforcement + initial-plan assistant_reply resync.

Production bug: user asked for a "16 unit plan", but the LLM produced 5
courses totaling 22 units and the chat reply hallucinated "four courses,
16-unit plan". The system_instruction tells the model to honor unit caps,
but that's a soft constraint and Gemini routinely ignores it.

These tests pin a deterministic Python-side fix:

1. ``_extract_unit_cap`` parses common ways students state a cap.
2. ``_enforce_unit_cap`` drops courses (tail first, lab/lecture pairs as
   a single group) until ``total_units <= cap``.
3. ``_resync_assistant_reply`` rewrites the LLM's chat reply when it
   mentions a course or unit count that disagrees with the final
   ``recommended`` / ``total_units`` (initial plans only — follow-ups
   already go through ``_sync_followup_assistant_reply``).
4. ``run_planning_agent`` end-to-end: a 5-course / 22-unit hallucination
   with chat reply "16-unit plan" gets trimmed AND the chat reply is
   rewritten so it matches the trimmed list.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from agents import planning_agent
from agents.planning_agent import (
    _enforce_unit_cap,
    _extract_unit_cap,
    _resync_assistant_reply,
)


def _rec(code, units=4, **extra):
    base = {"course": code, "units": units, "title": code, "category": "x", "reason": "y"}
    base.update(extra)
    return base


# ── _extract_unit_cap ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "preference,expected",
    [
        ("give me a 16 unit plan", 16),
        ("I want a 16-unit plan", 16),
        ("16units please", 16),
        ("under 20 units", 20),
        ("max 12 units", 12),
        ("no more than 18 units", 18),
        ("at most 14 units this quarter", 14),
        ("cap at 15 units", 15),
        ("limit to 13 units", 13),
        ("less than 19 units", 19),
        ("不超过 18 单元", 18),
        ("最多 16 学分", 16),
    ],
)
def test_extract_unit_cap_matches_common_phrases(preference, expected):
    assert _extract_unit_cap(preference) == expected


@pytest.mark.parametrize(
    "preference",
    [
        "",
        "mornings only, no Fridays",
        "I want fewer labs",
        "for 16 weeks of school",       # "16 weeks" is NOT a unit cap
        "section 16 of CSEN 174",       # course context, not a cap
    ],
)
def test_extract_unit_cap_returns_none_when_unclear(preference):
    assert _extract_unit_cap(preference) is None


def test_extract_unit_cap_picks_tightest_when_two_independent_caps():
    # Two separate cap statements: 18 is the looser one, 12 is the binding cap.
    assert _extract_unit_cap("under 18 units, but really max 12 units") == 12


# ── _enforce_unit_cap ────────────────────────────────────────────────────────


def test_enforce_unit_cap_passthrough_when_under_cap():
    plan = [_rec("THTR 189", 5), _rec("COMM 131D", 5), _rec("ENGR 111", 3)]
    out, dropped = _enforce_unit_cap(plan, 16)
    assert dropped == []
    assert [r["course"] for r in out] == ["THTR 189", "COMM 131D", "ENGR 111"]


def test_enforce_unit_cap_no_cap_is_noop():
    plan = [_rec("THTR 189", 5), _rec("RSOC 99", 4)]
    out, dropped = _enforce_unit_cap(plan, None)
    assert dropped == []
    assert len(out) == 2


def test_enforce_unit_cap_drops_tail_first_until_under_cap():
    """Production case: 22-unit plan asked for under 16 → drop tail."""
    plan = [
        _rec("THTR 189", 5),
        _rec("COMM 131D", 5),
        _rec("ENGR 111", 3),
        _rec("MGMT 110", 5),
        _rec("RSOC 99", 4),
    ]
    out, dropped = _enforce_unit_cap(plan, 16)
    total = sum(r["units"] for r in out)
    assert total <= 16
    assert "RSOC 99" in dropped
    # Earlier courses are preserved
    assert "THTR 189" in {r["course"] for r in out}


def test_enforce_unit_cap_drops_lab_with_lecture_as_one_group():
    """If the tail item is a lab, its lecture goes with it; vice versa."""
    plan = [
        _rec("CSEN 161", 4),
        _rec("CSEN 174", 4),
        _rec("CSEN 194", 4),
        _rec("CSEN 194L", 1),  # tail = lab → lecture must go too
    ]
    out, dropped = _enforce_unit_cap(plan, 12)
    codes = {r["course"] for r in out}
    assert "CSEN 194" not in codes
    assert "CSEN 194L" not in codes
    assert "CSEN 161" in codes
    assert "CSEN 174" in codes


def test_enforce_unit_cap_lecture_tail_drops_lab_partner_too():
    """Reverse: lecture is at the tail, lab earlier in the list."""
    plan = [
        _rec("CSEN 194L", 1),  # lab earlier
        _rec("CSEN 161", 4),
        _rec("CSEN 174", 4),
        _rec("CSEN 194", 4),   # lecture at tail
    ]
    out, dropped = _enforce_unit_cap(plan, 12)
    codes = {r["course"] for r in out}
    # CSEN 194 + CSEN 194L should both be gone (paired drop)
    assert "CSEN 194" not in codes
    assert "CSEN 194L" not in codes


# ── _resync_assistant_reply ──────────────────────────────────────────────────


def test_resync_rewrites_reply_when_unit_count_disagrees():
    """LLM said '16-unit plan' but recommended sums to 22 → rewrite."""
    parsed = {
        "recommended": [
            _rec("THTR 189", 5), _rec("COMM 131D", 5), _rec("ENGR 111", 3),
            _rec("MGMT 110", 5), _rec("RSOC 99", 4),
        ],
        "total_units": 22,
        "assistant_reply": "I've put together a 16-unit plan with four courses: THTR 189, COMM 131D, ENGR 111, MGMT 110.",
    }
    _resync_assistant_reply(parsed)
    reply = parsed["assistant_reply"]
    # New reply must reference the actual total
    assert "22" in reply
    # And must NOT claim 16 anymore
    assert "16-unit" not in reply and "16 unit" not in reply


def test_resync_rewrites_reply_when_codes_disagree():
    """LLM mentioned a course that's not in recommended → rewrite."""
    parsed = {
        "recommended": [_rec("THTR 189", 5)],
        "total_units": 5,
        "assistant_reply": "I added CSEN 174 to your plan.",
    }
    _resync_assistant_reply(parsed)
    # CSEN 174 must not be in the new reply
    assert "CSEN 174" not in parsed["assistant_reply"]
    assert "THTR 189" in parsed["assistant_reply"]


def test_resync_leaves_consistent_reply_alone():
    parsed = {
        "recommended": [_rec("THTR 189", 5), _rec("COMM 131D", 5)],
        "total_units": 10,
        "assistant_reply": "Here's a 10-unit plan with THTR 189 and COMM 131D.",
    }
    _resync_assistant_reply(parsed)
    # Reply unchanged because it agrees with recommended + total_units
    assert parsed["assistant_reply"] == "Here's a 10-unit plan with THTR 189 and COMM 131D."


def test_resync_empty_recommended_is_noop():
    parsed = {"recommended": [], "total_units": 0, "assistant_reply": "hi"}
    _resync_assistant_reply(parsed)
    assert parsed["assistant_reply"] == "hi"


# ── End-to-end: run_planning_agent applies cap + resync on initial plan ─────


def _stub_client(reply: dict):
    class _Models:
        def generate_content(self, model, contents, config):
            return SimpleNamespace(text=json.dumps(reply))

    class _Client:
        models = _Models()

    return _Client()


def test_initial_plan_with_unit_cap_trims_and_rewrites_reply(monkeypatch):
    """Real production regression: user asked for '16 unit plan' but
    the LLM produced 5 courses / 22 units, with a chat reply claiming
    "four courses, 16-unit plan". After the fix:

    - recommended is trimmed to <= 16 units
    - assistant_reply matches the trimmed list and its total
    - a warning surfaces the trim
    """
    llm_reply = {
        "recommended": [
            {"course": "THTR 189", "title": "Social Justice and the Arts", "category": "Core", "units": 5, "reason": "ELSJ"},
            {"course": "COMM 131D", "title": "Short Documentary Production", "category": "Core", "units": 5, "reason": "ELSJ"},
            {"course": "ENGR 111", "title": "STEM Outreach", "category": "Core", "units": 3, "reason": "ELSJ"},
            {"course": "MGMT 110", "title": "Global Microfinance", "category": "Core", "units": 5, "reason": "ELSJ"},
            {"course": "RSOC 99", "title": "Sociology of Religion", "category": "Core", "units": 4, "reason": "RTC"},
        ],
        "total_units": 22,
        "advice": "ok",
        "assistant_reply": "I've put together a 16-unit plan for you this term with four courses: THTR 189, COMM 131D, ENGR 111, and MGMT 110.",
    }

    monkeypatch.setattr(planning_agent, "get_genai_client", lambda **_: _stub_client(llm_reply))
    # Bypass schedule/required-codes validation so the LLM list survives.
    monkeypatch.setattr(planning_agent, "load_schedule_section_index", lambda: {})
    monkeypatch.setattr(planning_agent, "load_category_course_index", lambda: {})
    monkeypatch.setattr(planning_agent, "load_course_titles_index", lambda: {})
    monkeypatch.setattr(planning_agent, "load_course_units_index", lambda: {})

    result = planning_agent.run_planning_agent(
        missing_details=[
            {"course": "THTR 189", "category": "Core", "units": 5},
            {"course": "COMM 131D", "category": "Core", "units": 5},
            {"course": "ENGR 111", "category": "Core", "units": 3},
            {"course": "MGMT 110", "category": "Core", "units": 5},
            {"course": "RSOC 99", "category": "Core", "units": 4},
        ],
        user_preference="give me a 16 unit plan",
        previous_plan=None,
    )

    # 1. Trimmed to <= 16 units.
    assert result["total_units"] <= 16
    assert sum(r["units"] for r in result["recommended"]) == result["total_units"]

    # 2. assistant_reply no longer claims the false "16-unit / four courses".
    reply = result["assistant_reply"]
    final_codes = {r["course"] for r in result["recommended"]}
    # Reply only mentions codes actually in recommended
    import re
    for m in re.finditer(r"\b([A-Z]{2,6})\s*(\d{1,3}[A-Z]?)\b", reply):
        code = f"{m.group(1)} {m.group(2)}"
        assert code in final_codes, f"reply mentions {code} which is not in recommended"
    # Reply quotes the actual total (not the original hallucinated 22)
    assert str(result["total_units"]) in reply

    # 3. A warning surfaces the trim.
    codes = {w.get("code") for w in result.get("warnings", [])}
    assert "unit_cap_enforced" in codes
