"""Course-tag parsing and category→course reverse index.

The schedule xlsx has a free-form ``Course Tags`` column shaped like:

    Core Explorations :: RTC 3 | Religion, Theology and Culture 3

    Core Integrations :: ELSJ | Experiential Learning for Social Justice

    Pathways :: Applied Ethics

``_parse_course_tag_codes`` splits these into the short code + the long
description (both indexed) so the planning agent can match either side
of a Workday requirement string against the same key set.

``load_category_course_index`` then walks the xlsx and builds a reverse
map ``{normalized_tag: [course_codes]}`` used by the open-requirement
resolver. End-to-end smoke tests run against the checked-in xlsx so a
breaking column rename in real data fails the build.
"""

from __future__ import annotations

import pytest

from utils.scu_course_schedule_xlsx import (
    _parse_course_tag_codes,
    load_category_course_index,
)


# ── _parse_course_tag_codes ──────────────────────────────────────────────────


def test_parse_extracts_short_code_and_long_description():
    """Both halves of ``X :: Y | Z`` are returned, so callers can match
    by either the short tag or the human-readable description."""
    cell = "Core Explorations :: RTC 3 | Religion, Theology and Culture 3"
    out = _parse_course_tag_codes(cell)
    assert "RTC 3" in out
    assert "Religion, Theology and Culture 3" in out


def test_parse_multiple_lines():
    cell = (
        "Core Explorations :: RTC 3 | Religion, Theology and Culture 3\n\n"
        "Core Integrations :: ELSJ | Experiential Learning for Social Justice\n\n"
        "Pathways :: Applied Ethics"
    )
    out = _parse_course_tag_codes(cell)
    assert "RTC 3" in out
    assert "ELSJ" in out
    assert "Experiential Learning for Social Justice" in out
    assert "Applied Ethics" in out  # no "|" → whole-part kept


def test_parse_handles_no_double_colon():
    """A bare tag with no ``::`` group prefix is kept verbatim."""
    out = _parse_course_tag_codes("Just A Tag")
    assert out == ["Just A Tag"]


def test_parse_handles_empty_and_none():
    assert _parse_course_tag_codes("") == []
    assert _parse_course_tag_codes(None) == []  # type: ignore[arg-type]


def test_parse_strips_surrounding_whitespace():
    out = _parse_course_tag_codes("  Core :: Foo  |  Long Foo  \n")
    assert "Foo" in out
    assert "Long Foo" in out


def test_parse_handles_pipe_with_no_short_code():
    """``"X :: | Foo"`` gives back just the long description."""
    out = _parse_course_tag_codes("X :: | Foo")
    assert "Foo" in out


# ── load_category_course_index (real xlsx) ───────────────────────────────────


@pytest.fixture(scope="module")
def cat_idx() -> dict[str, list[str]]:
    """Build the index once for all integration tests."""
    return load_category_course_index()


def test_index_loads_non_empty(cat_idx):
    """Schedule xlsx must contain Course Tags column with parseable rows."""
    assert cat_idx, "Course Tags index unexpectedly empty"


def test_index_has_user_open_requirements(cat_idx):
    """The four open Core requirements the live transcript shipped with
    (RTC 3, ELSJ, Advanced Writing, Arts) must all map to ≥1 candidate."""
    assert cat_idx.get("rtc 3"), "no candidates for RTC 3 — regression"
    assert cat_idx.get("elsj"), "no candidates for ELSJ — regression"
    assert cat_idx.get("advanced writing"), "no candidates for Advanced Writing"


def test_sctr_128_is_double_tagged(cat_idx):
    """SCTR 128 satisfies both RTC 3 and ELSJ — this double-tag is the
    feature the user surfaced repeatedly ("可以更快毕业啊")."""
    assert "SCTR 128" in cat_idx.get("rtc 3", []), "SCTR 128 missing from RTC 3"
    assert "SCTR 128" in cat_idx.get("elsj", []), "SCTR 128 missing from ELSJ"
    # And from the long-form description too (substring fallback path)
    assert "SCTR 128" in cat_idx.get("religion, theology and culture 3", [])
    assert "SCTR 128" in cat_idx.get("experiential learning for social justice", [])


def test_index_keys_are_lowercase(cat_idx):
    """All keys are lower-cased for case-insensitive lookup."""
    for k in cat_idx.keys():
        assert k == k.lower(), f"key not lower-case: {k!r}"


def test_index_includes_csen_coen_alias(cat_idx):
    """If CSEN X appears under a tag, COEN X must too (and vice versa)."""
    for key, courses in cat_idx.items():
        codes = set(courses)
        for c in courses:
            parts = c.split()
            if len(parts) != 2:
                continue
            subj, num = parts
            if subj == "CSEN":
                assert f"COEN {num}" in codes, f"missing COEN alias for {c} under {key!r}"
            elif subj == "COEN":
                assert f"CSEN {num}" in codes, f"missing CSEN alias for {c} under {key!r}"
