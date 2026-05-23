"""Follow-up edits must be TARGETED diffs (AGENTS.md R7).

A "replace ECEN 153 with a Chinese class" follow-up dropped the unrelated
CSEN courses, duplicated the replacement, and produced an inconsistent
total — because the whole plan was re-emitted by the LLM. These tests pin
the deterministic reconcile that:
  - dedups the LLM's list,
  - re-adds any CURRENT STATE course the user did NOT name for removal.
"""

from __future__ import annotations

from agents.planning_agent import (
    _named_removal_codes,
    _reconcile_followup_edit,
)


def _rec(code, units=4):
    return {"course": code, "units": units, "title": code, "category": "x", "reason": "y"}


# ── _named_removal_codes ─────────────────────────────────────────────────────


def test_named_removal_extracts_code_with_space():
    out = _named_removal_codes("replace ECEN 153 with a Chinese class")
    assert "ECEN 153" in out


def test_named_removal_extracts_code_without_space():
    out = _named_removal_codes("ecen153换成enrichment chinese class")
    assert "ECEN 153" in out


def test_named_removal_includes_lab_partner_and_alias():
    out = _named_removal_codes("drop ECEN 153")
    assert "ECEN 153" in out
    assert "ECEN 153L" in out      # lab partner
    assert "ELEN 153" in out       # subject alias
    assert "ELEN 153L" in out      # alias lab


def test_named_removal_empty_when_no_codes():
    assert _named_removal_codes("make it lighter please") == set()


# ── _reconcile_followup_edit ─────────────────────────────────────────────────


_PREV = {
    "recommended": [
        _rec("CSEN 122"), _rec("CSEN 122L", 1),
        _rec("CSEN 194", 4), _rec("CSEN 194L", 1),
        _rec("ECEN 153", 4), _rec("ECEN 153L", 1),
        _rec("ENGL 181", 4),
    ],
    "total_units": 19,
}


def test_swap_preserves_unrelated_courses():
    """The exact production bug: replace ECEN 153 → CHST 4, but the LLM
    dropped the CSEN courses. Reconcile must bring them back."""
    llm_out = [_rec("CHST 4"), _rec("ENGL 181")]  # LLM mangled it
    out = _reconcile_followup_edit(llm_out, _PREV, "ecen153换成enrichment chinese class")
    codes = {r["course"] for r in out}
    # Unrelated CSEN courses preserved
    assert {"CSEN 122", "CSEN 122L", "CSEN 194", "CSEN 194L"} <= codes
    # Replacement present, ENGL 181 kept
    assert "CHST 4" in codes
    assert "ENGL 181" in codes
    # ECEN 153 + its lab were named for removal → gone
    assert "ECEN 153" not in codes
    assert "ECEN 153L" not in codes


def test_dedup_removes_repeated_course():
    """LLM repeated CHST 4 twice — only one survives."""
    llm_out = [_rec("CHST 4"), _rec("ENGL 181"), _rec("CHST 4")]
    out = _reconcile_followup_edit(llm_out, _PREV, "ecen153换成chinese")
    chst = [r for r in out if r["course"] == "CHST 4"]
    assert len(chst) == 1


def test_unnamed_removal_is_reverted():
    """If the LLM drops a course the user never mentioned, it's restored."""
    # User only asked about ENGL; LLM wrongly dropped CSEN 194.
    llm_out = [_rec("CSEN 122"), _rec("CSEN 122L", 1), _rec("ECEN 153"),
               _rec("ECEN 153L", 1), _rec("ENGL 181")]
    out = _reconcile_followup_edit(llm_out, _PREV, "swap ENGL 181 for something else")
    codes = {r["course"] for r in out}
    assert "CSEN 194" in codes      # never named → restored
    assert "CSEN 194L" in codes


def test_no_previous_plan_just_dedups():
    llm_out = [_rec("CSEN 122"), _rec("CSEN 122")]
    out = _reconcile_followup_edit(llm_out, None, "plan me")
    assert [r["course"] for r in out] == ["CSEN 122"]


def test_first_turn_passthrough_with_dedup():
    llm_out = [_rec("CSEN 122"), _rec("ENGL 181")]
    out = _reconcile_followup_edit(llm_out, {}, "balanced")
    assert {r["course"] for r in out} == {"CSEN 122", "ENGL 181"}


def test_named_removal_respected_even_if_llm_kept_it():
    """If the user said remove ECEN 153 but the LLM kept it, reconcile does
    NOT force-remove it (the LLM's list is authoritative for what's IN);
    reconcile only prevents *unauthorized drops*. ECEN 153 stays because
    the LLM included it — the user can re-ask. This documents the boundary."""
    llm_out = [_rec("CSEN 122"), _rec("ECEN 153"), _rec("ENGL 181")]
    out = _reconcile_followup_edit(llm_out, _PREV, "drop ECEN 153")
    codes = {r["course"] for r in out}
    # ECEN 153 present because the LLM emitted it; reconcile doesn't delete.
    assert "ECEN 153" in codes
    # but unrelated dropped courses are still restored
    assert "CSEN 194" in codes
