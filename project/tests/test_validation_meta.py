"""PR1 instrumentation: ``meta.validation`` audit on every plan response.

Locks the production audit shape so the eval dashboard and any future
A/B comparison between the legacy engine and ``constrained_v2`` can
reliably compute hallucination, repair, and giveup rates.

Contract:
  - Every successful ``run_planning_agent`` response carries
    ``meta.validation`` with keys
    ``{engine, candidate_count, rejected, repaired, deferred_requirements,
       removed_completed, dropped_for_unit_cap}``.
  - ``_partition_recommended(audit=[...])`` appends one record per
    rejection with ``{course, reason, category, round}``.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

from agents import planning_agent


def _slot(days, start, end, instructors=()):
    return {
        "instructors": list(instructors),
        "meeting_days": list(days),
        "meeting_start_min": start,
        "meeting_end_min": end,
    }


def _stub_client(replies: list[dict]):
    """Return a fake Gemini client that yields each reply in sequence."""
    iter_replies = iter(replies)

    class _Models:
        def generate_content(self, model, contents, config):  # noqa: D401
            try:
                payload = next(iter_replies)
            except StopIteration:
                payload = replies[-1]
            return SimpleNamespace(text=json.dumps(payload))

    class _Client:
        models = _Models()

    return _Client()


# ── _partition_recommended audit hook ────────────────────────────────────────


def test_partition_audit_records_each_rejection_with_round_label():
    sched = {
        ("CSEN", "122"): _slot([0, 2, 4], 75, 140),
        ("CSEN", "194"): _slot([1, 3], 150, 215),
    }
    recommended = [
        {"course": "CSEN 122", "category": "Major", "units": 4},
        {"course": "PHIL 12", "category": "Applied Ethics", "units": 4},
        {"course": "CSEN 999", "category": "Major", "units": 4},
    ]
    audit: list[dict] = []
    valid, rejected = planning_agent._partition_recommended(
        recommended,
        sched,
        required_codes={"CSEN 122", "CSEN 194"},
        audit=audit,
        round_label="initial",
    )
    assert [v["course"] for v in valid] == ["CSEN 122"]
    assert len(rejected) == 2
    assert len(audit) == 2
    reasons = {(r["course"], r["reason"], r["round"]) for r in audit}
    assert ("PHIL 12", "not_a_real_requirement", "initial") in reasons
    assert ("CSEN 999", "not_a_real_requirement", "initial") in reasons
    # Every audit row records the category so dashboards can group by it.
    assert all("category" in r for r in audit)


def test_partition_audit_distinguishes_repair_rounds():
    sched = {("CSEN", "122"): _slot([0, 2, 4], 75, 140)}
    audit: list[dict] = []
    planning_agent._partition_recommended(
        [{"course": "FAKE 1", "category": "Major", "units": 4}],
        sched,
        required_codes={"CSEN 122"},
        audit=audit,
        round_label="repair_1",
    )
    assert audit and audit[0]["round"] == "repair_1"


def test_partition_without_audit_does_not_break_existing_callers():
    """Backwards compatibility: omitting ``audit`` must keep the legacy
    signature working unchanged (other tests rely on this)."""
    sched = {("CSEN", "122"): _slot([0, 2, 4], 75, 140)}
    valid, rejected = planning_agent._partition_recommended(
        [{"course": "CSEN 122", "category": "Major", "units": 4}],
        sched,
        required_codes=None,
    )
    assert [v["course"] for v in valid] == ["CSEN 122"]
    assert rejected == []


# ── run_planning_agent meta.validation ───────────────────────────────────────


def test_run_planning_agent_emits_validation_meta(monkeypatch):
    """A normal (no-hallucination) plan must still ship the audit block."""
    reply = {
        "recommended": [
            {"course": "CSEN 174", "title": "Software Engineering",
             "category": "Major", "units": 4, "reason": "core"},
        ],
        "total_units": 4,
        "advice": "ok",
        "assistant_reply": "Built a 4-unit plan: CSEN 174.",
    }
    fake_sched = {
        ("CSEN", "174"): _slot([0, 2, 4], 75, 140),
        ("COEN", "174"): _slot([0, 2, 4], 75, 140),
    }
    monkeypatch.setattr(planning_agent, "get_genai_client", lambda **_kw: _stub_client([reply]))
    monkeypatch.setattr(planning_agent, "load_schedule_section_index", lambda: fake_sched)
    monkeypatch.setattr(planning_agent, "load_category_course_index", lambda: {})
    monkeypatch.setattr(planning_agent, "load_course_titles_index", lambda: {})
    monkeypatch.setattr(planning_agent, "load_course_units_index", lambda: {})

    out = planning_agent.run_planning_agent(
        missing_details=[{"course": "CSEN 174", "category": "Major", "units": 4}],
        user_preference="balanced",
    )
    meta = out.get("meta") or {}
    validation = meta.get("validation") or {}
    assert validation.get("engine") == "legacy"
    assert validation.get("candidate_count", -1) >= 1
    assert validation.get("rejected") == []
    assert validation.get("repaired") == []
    assert validation.get("deferred_requirements") == []
    # Defensive: keys are stable so dashboards don't break.
    assert set(validation.keys()) >= {
        "engine", "candidate_count", "rejected", "repaired",
        "deferred_requirements", "removed_completed", "dropped_for_unit_cap",
    }


def test_run_planning_agent_records_hallucination_in_validation(monkeypatch):
    """LLM emits a real-requirement course AND a hallucinated one. The
    audit must contain the hallucination with a recognisable reason; the
    second-round repair LLM provides a valid replacement and the audit
    records both."""
    initial = {
        "recommended": [
            {"course": "CSEN 174", "title": "Software Engineering",
             "category": "Major", "units": 4, "reason": "core"},
            {"course": "PHIL 12", "title": "Ethics",
             "category": "Applied Ethics", "units": 4, "reason": "core"},
        ],
        "total_units": 8,
        "advice": "ok",
        "assistant_reply": "Built a plan.",
    }
    repair = {
        "recommended": [
            {"course": "SCTR 128", "title": "Religion, Violence, Nonviolence",
             "category": "Applied Ethics", "units": 4, "reason": "core"},
        ],
        "total_units": 4,
        "advice": "fixed",
        "assistant_reply": "Swapped in SCTR 128.",
    }
    fake_sched = {
        ("CSEN", "174"): _slot([0, 2, 4], 75, 140),
        ("COEN", "174"): _slot([0, 2, 4], 75, 140),
        ("SCTR", "128"): _slot([1, 3], 200, 290),
    }
    monkeypatch.setattr(
        planning_agent, "get_genai_client",
        lambda **_kw: _stub_client([initial, repair]),
    )
    monkeypatch.setattr(planning_agent, "load_schedule_section_index", lambda: fake_sched)
    # Wire the open-Core path: SCTR 128 covers "applied ethics"
    monkeypatch.setattr(
        planning_agent, "load_category_course_index",
        lambda: {"applied ethics": ["SCTR 128"]},
    )
    monkeypatch.setattr(planning_agent, "load_course_titles_index", lambda: {})
    monkeypatch.setattr(planning_agent, "load_course_units_index", lambda: {})

    out = planning_agent.run_planning_agent(
        missing_details=[
            {"course": "CSEN 174", "category": "Major", "units": 4},
            {"category": "Core: ENGR: Applied Ethics",
             "requirement": "Core: ENGR: Applied Ethics"},
        ],
        user_preference="knock out core",
    )
    validation = (out.get("meta") or {}).get("validation") or {}
    reasons = {(r["course"], r["reason"]) for r in validation.get("rejected") or []}
    assert ("PHIL 12", "not_a_real_requirement") in reasons
    repaired_codes = {r["course"] for r in validation.get("repaired") or []}
    assert "SCTR 128" in repaired_codes
    # The final plan should include the real course plus the repair.
    final_codes = {r["course"] for r in out.get("recommended") or []}
    assert final_codes == {"CSEN 174", "SCTR 128"}
