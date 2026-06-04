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
    _is_pure_question_followup,
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


def test_named_removal_empty_for_bare_question():
    """A question that merely mentions a code authorizes no removal.

    Production bug: "那 thtr189 呢" (what about THTR 189?) was parsed as
    "remove THTR 189" and the course was silently dropped.
    """
    assert _named_removal_codes("那 thtr189 呢") == set()
    assert _named_removal_codes("why did you pick CSEN 122?") == set()
    assert _named_removal_codes("ECEN 153 looks hard") == set()


def test_named_removal_still_extracts_with_intent():
    """A real removal verb still extracts the named code (+lab+alias)."""
    assert "ECEN 153" in _named_removal_codes("drop ECEN 153")
    assert "ECEN 153" in _named_removal_codes("ecen153换成 chinese")
    assert "THTR 189" in _named_removal_codes("remove thtr189")


# ── _is_pure_question_followup ───────────────────────────────────────────────


def test_pure_question_detected():
    assert _is_pure_question_followup("那 thtr189 呢")
    assert _is_pure_question_followup("为什么选 CSEN 122？")
    assert _is_pure_question_followup("why these courses?")


def test_edit_request_is_not_pure_question():
    """A question that also asks to edit is NOT frozen."""
    assert not _is_pure_question_followup("why not drop ECEN 153?")
    assert not _is_pure_question_followup("can you add a lighter class?")


def test_explicit_add_question_is_not_frozen():
    """A question with an explicit add verb still edits the plan."""
    assert not _is_pure_question_followup("can you add a chinese class?")
    assert not _is_pure_question_followup("能不能加一节中文课？")


def test_bare_enrichment_question_freezes():
    """'Any Chinese courses I could take?' (no add verb) freezes; the student
    adds explicitly on a later turn — safer R7 default."""
    assert _is_pure_question_followup("any chinese courses I could take?")


def test_statement_without_question_is_not_pure_question():
    assert not _is_pure_question_followup("make it lighter please")


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


def test_swap_to_named_code_keeps_replacement():
    """Production bug: "把 X 换成 Y" named BOTH X and Y for removal, so the
    new course Y was deleted by the hard-removal rule and the swap silently
    did nothing. The replacement (named, but absent from the previous plan)
    must survive; only the previous-plan course X is removed."""
    llm_out = [_rec("CSEN 20"), _rec("ENGL 181")]  # LLM swapped ECEN 153 -> CSEN 20
    out = _reconcile_followup_edit(llm_out, _PREV, "把 ECEN 153 换成 CSEN 20")
    codes = {r["course"] for r in out}
    assert "CSEN 20" in codes        # replacement kept (was NOT in previous plan)
    assert "ECEN 153" not in codes   # swapped-out course removed
    assert "ECEN 153L" not in codes  # its lab partner too
    # Unrelated previous courses preserved
    assert {"CSEN 122", "CSEN 122L", "CSEN 194", "CSEN 194L", "ENGL 181"} <= codes


def test_english_swap_for_named_code_keeps_replacement():
    """Same bug via English 'replace X with Y' / 'swap X for Y'."""
    llm_out = [_rec("CSEN 20"), _rec("ENGL 181")]
    out = _reconcile_followup_edit(llm_out, _PREV, "replace ECEN 153 with CSEN 20")
    codes = {r["course"] for r in out}
    assert "CSEN 20" in codes
    assert "ECEN 153" not in codes


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
    """Hard rule: if the user explicitly named a course to remove, it must be removed
    deterministically even if the LLM kept it."""
    llm_out = [_rec("CSEN 122"), _rec("ECEN 153"), _rec("ENGL 181")]
    out = _reconcile_followup_edit(llm_out, _PREV, "drop ECEN 153")
    codes = {r["course"] for r in out}
    assert "ECEN 153" not in codes
    assert "ECEN 153L" not in codes
    # but unrelated dropped courses are still restored
    assert "CSEN 194" in codes


def test_pure_question_freezes_plan():
    """The production bug: "那 thtr189 呢" must NOT remove THTR 189.

    Even if the LLM mangles the list (drops THTR 189, adds ENGR 111), the
    pure-question freeze returns CURRENT STATE unchanged.
    """
    prev = {
        "recommended": [
            _rec("ECEN 153", 4), _rec("ECEN 153L", 1),
            _rec("GNSX 154A", 5), _rec("THTR 189", 5),
        ],
        "total_units": 15,
    }
    # LLM wrongly removed THTR 189 and added ENGR 111.
    llm_out = [_rec("ECEN 153", 4), _rec("ECEN 153L", 1),
               _rec("GNSX 154A", 5), _rec("ENGR 111", 3)]
    out = _reconcile_followup_edit(llm_out, prev, "那 thtr189 呢")
    codes = {r["course"] for r in out}
    assert codes == {"ECEN 153", "ECEN 153L", "GNSX 154A", "THTR 189"}
    assert "ENGR 111" not in codes  # not added on a question
    assert "THTR 189" in codes      # not removed on a question


def test_edit_question_still_edits():
    """A question with edit intent ('why not drop ECEN 153?') still removes it."""
    llm_out = [_rec("CSEN 122"), _rec("CSEN 122L", 1), _rec("CSEN 194", 4),
               _rec("CSEN 194L", 1), _rec("ENGL 181")]
    out = _reconcile_followup_edit(llm_out, _PREV, "why not drop ECEN 153?")
    codes = {r["course"] for r in out}
    assert "ECEN 153" not in codes
    assert "ECEN 153L" not in codes
