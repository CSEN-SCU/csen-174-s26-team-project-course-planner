"""Lab co-requirement pairing works with Workday-style missing_details.

The existing test_lab_pairing.py uses items with explicit ``course="CSEN 194"``
fields. Real Workday transcripts ship ``course=None`` for every row — the
codes live inside the ``requirement`` text (e.g. ``"CSEN/COEN 194/L"``).
The lab pairer originally built its lookup with ``item.get("course")``,
which silently became an empty index for Workday items and let labs vanish
on follow-up turns.

These tests pin the regression: the pairer must use ``_resolve_item_codes``
under the hood and survive a CSEN/COEN alias swap on the partner lookup.
"""

from __future__ import annotations

from agents import planning_agent


# Workday-style item: ``course=None``; codes only appear in ``requirement``.
def _workday(requirement: str, units: int = 5) -> dict:
    return {"course": None, "requirement": requirement, "status": "Not Satisfied", "units": units}


# ── md_by_code lookup (the regression's root cause) ──────────────────────────


def test_pair_resolves_partner_via_extracted_codes_workday_format():
    """Lecture-only recommendation must still pair the lab even when
    every missing_details item has ``course=None``."""
    recommended = [
        {"course": "CSEN 194", "category": "Senior Design", "units": 3, "reason": "kickoff"},
    ]
    missing_details = [
        _workday("Computer Science and Engineering Major: CSEN/COEN 194/L", units=5),
    ]

    paired = planning_agent._pair_lab_corequirements(recommended, missing_details)

    codes = {item["course"] for item in paired}
    assert "CSEN 194L" in codes, "lab partner must be auto-added for Workday format"


def test_pair_handles_ampersand_continuation():
    """`CSEN/COEN 122 & 122L` must surface 122L when 122 is recommended."""
    recommended = [
        {"course": "CSEN 122", "category": "Major", "units": 4, "reason": "core"},
    ]
    missing_details = [
        _workday("Computer Science and Engineering Major: CSEN/COEN 122 & 122L"),
    ]

    paired = planning_agent._pair_lab_corequirements(recommended, missing_details)
    assert {"CSEN 122", "CSEN 122L"} <= {i["course"] for i in paired}


def test_pair_uses_csen_coen_alias_for_partner_lookup():
    """If the requirement only mentions COEN but the LLM recommended CSEN
    (or vice versa), the alias swap must still find the partner.

    Using ``"COEN 194L"`` (lab-only) as the requirement text: the regex
    extracts only ``COEN 194L``, so when CSEN 194 is recommended the
    lookup for ``CSEN 194L`` misses and only the COEN alias finds it.
    """
    recommended = [
        {"course": "CSEN 194", "category": "Senior Design", "units": 3, "reason": "kickoff"},
    ]
    missing_details = [
        {"course": None, "requirement": "COEN 194L", "status": "Not Satisfied"},
    ]

    paired = planning_agent._pair_lab_corequirements(recommended, missing_details)
    codes = {item["course"] for item in paired}
    assert "COEN 194L" in codes or "CSEN 194L" in codes, (
        "alias swap should find COEN 194L when student already has CSEN 194 in plan"
    )


def test_extract_regex_does_not_handle_bare_ampersand_continuation():
    """Document a known regex limitation: ``"COEN 194 & 194L"`` (no slash
    subject group) only yields ``COEN 194``.  Real Workday transcripts
    always use the slash form ``"CSEN/COEN 194/L"`` or ``"CSEN/COEN 194
    & 194L"`` so this edge has never bitten us in production — but the
    test pins current behaviour so a future regex tweak can intentionally
    extend support and update this baseline."""
    from agents.planning_agent import _extract_codes_from_requirement
    assert _extract_codes_from_requirement("COEN 194 & 194L") == ["COEN 194"]


def test_pair_added_lab_carries_title_fallback():
    """Lab items added by the pairer need a non-empty title for the UI."""
    recommended = [
        {"course": "CSEN 122", "category": "Major", "units": 4, "reason": "core"},
    ]
    missing_details = [_workday("CSEN/COEN 122 & 122L")]

    paired = planning_agent._pair_lab_corequirements(recommended, missing_details)
    lab = next(i for i in paired if i["course"].endswith("122L"))
    assert lab.get("title"), "added lab must have a title (UI falls back if blank)"


def test_pair_does_not_duplicate_when_lab_already_recommended():
    recommended = [
        {"course": "CSEN 194", "category": "Senior Design", "units": 3, "reason": "kickoff"},
        {"course": "CSEN 194L", "category": "Senior Design", "units": 1, "reason": "lab"},
    ]
    missing_details = [_workday("CSEN/COEN 194/L")]

    paired = planning_agent._pair_lab_corequirements(recommended, missing_details)
    codes = [i["course"] for i in paired]
    assert codes.count("CSEN 194L") == 1
    assert len(paired) == 2


def test_pair_no_op_when_partner_not_in_any_requirement():
    """A standalone CSEN 9 with no lab in any requirement text → no pairing.

    Use a low number that doesn't trigger lab patterns elsewhere."""
    recommended = [
        {"course": "CSEN 9", "category": "Major", "units": 4, "reason": "intro"},
    ]
    # No 9L anywhere in the missing_details text
    missing_details = [_workday("CSEN 9 only")]

    paired = planning_agent._pair_lab_corequirements(recommended, missing_details)
    assert [i["course"] for i in paired] == ["CSEN 9"]
