"""Tests for ``_extract_codes_from_requirement`` regex extraction.

The Workday Academic Progress export has course codes embedded in free-form
``requirement`` strings rather than a separate code column (column 3 / D is
``Registrations Used`` — usually empty on the not-satisfied summary rows).
The planning agent leans on this regex to recover codes from text like:

    "Computer Science and Engineering Major: CSEN/COEN 122 & 122L"
    "ECEN/ELEN 153 & 153L"
    "CSEN/COEN 194/L"   ← shorthand for "194 & 194L"

If extraction drops a variant, the hallucination filter starts rejecting
legit LLM recommendations and the lab pairer silently no-ops — both of
which we hit in production earlier. These tests pin the wiring.
"""

from __future__ import annotations

import pytest

from agents.planning_agent import _extract_codes_from_requirement


def _extracted(text: str) -> set[str]:
    return set(_extract_codes_from_requirement(text))


def test_slash_subject_with_ampersand_lab():
    """CSEN/COEN 122 & 122L → both subjects, both numbers."""
    out = _extracted("Computer Science and Engineering Major: CSEN/COEN 122 & 122L")
    assert {"CSEN 122", "COEN 122", "CSEN 122L", "COEN 122L"} <= out


def test_slash_subject_with_slash_l_shorthand():
    """CSEN/COEN 194/L is shorthand for "194 & 194L" — must expand."""
    out = _extracted("CSEN/COEN 194/L")
    assert {"CSEN 194", "COEN 194", "CSEN 194L", "COEN 194L"} <= out


def test_ecen_elen_alias_pair():
    """ECEN/ELEN 153 & 153L — both alias subjects, both course numbers."""
    out = _extracted("ECEN/ELEN 153 & 153L")
    assert {"ECEN 153", "ELEN 153", "ECEN 153L", "ELEN 153L"} <= out


def test_plain_subject_number_pair():
    """Simple "SUBJ NUM" still works without slash group."""
    out = _extracted("CSEN 140L")
    assert "CSEN 140L" in out


def test_no_garbage_subjects_from_long_words():
    """ENGINEERING is 11 letters and must not be parsed as a subject token.

    The regex caps subjects at {2,6} letters precisely so prose like
    'Computer Science and Engineering Major' doesn't pollute the result."""
    out = _extracted("Computer Science and Engineering Major: requirements pending")
    # No 7+ letter "subject" tokens
    for c in out:
        subj = c.split()[0]
        assert 2 <= len(subj) <= 6, f"unexpected long subject: {c!r}"


def test_empty_and_whitespace_safe():
    assert _extracted("") == set()
    assert _extracted("   ") == set()


def test_lowercase_input_is_normalised():
    """The regex normalises to uppercase so case-insensitive inputs work."""
    out = _extracted("csen/coen 122 & 122l")
    assert {"CSEN 122", "COEN 122", "CSEN 122L", "COEN 122L"} <= out


def test_returns_unique_codes_only():
    """No duplicate entries when the same code is mentioned twice."""
    codes = _extract_codes_from_requirement("CSEN 100 and also CSEN 100")
    assert codes.count("CSEN 100") == 1


def test_does_not_invent_zeros_or_letters():
    """Extraction must not invent variants like CSEN 100A from CSEN 100."""
    out = _extracted("CSEN 100")
    assert "CSEN 100A" not in out
    assert "CSEN 100B" not in out


def test_three_letter_pseudo_subject_passes_regex():
    """Edge case: 'RTC 3' looks like SUBJ NUM and IS extracted.

    The downstream code uses the schedule_index ``real_subjects`` set to
    filter these out (RTC is a Core tag, not a real SCU course subject).
    Documenting the behaviour here so future regressions on the
    *downstream* filter are easy to localise."""
    out = _extracted("Core: ENGR: RTC 3")
    assert "RTC 3" in out
