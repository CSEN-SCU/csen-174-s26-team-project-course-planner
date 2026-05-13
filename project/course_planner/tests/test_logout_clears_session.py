"""auth/streamlit_auth.clear_user_scoped_session must wipe every key that
identifies a previous user's data, so user A's missing_details / planning
history can't bleed into user B's next session.

We can't render the full Streamlit app in unit tests, but we can drive
`clear_user_scoped_session()` against a stub session_state that mirrors
the keys the real app sets in main.py.
"""

from __future__ import annotations

import pytest


@pytest.fixture()
def stub_session_state(monkeypatch):
    """Replace `streamlit.session_state` with a plain dict for testing."""
    import streamlit as st

    state: dict = {}

    class _DictState(dict):
        def __delitem__(self, key):
            super().__delitem__(key)

    fake = _DictState()
    monkeypatch.setattr(st, "session_state", fake)
    return fake


def test_clear_user_scoped_session_removes_user_state(stub_session_state):
    from auth import streamlit_auth

    stub_session_state.update({
        "user_id": 42,
        "username": "alice",
        "authentication_status": True,
        "name": "Alice Q. User",
        "email": "alice@example.com",
        "missing_details": [{"course": "COEN 146"}],
        "parsed_rows": [{"requirement": "X", "status": "Satisfied"}],
        "transcript_progress_snapshot": {"course_codes": []},
        "planning_result": {"recommended": []},
        "enriched_courses": [{"course": "COEN 146"}],
        "_recommended_enrichment_fp": "abc",
        "course_schedule_map": {"COEN 146": "M W F | 9:00 AM - 9:50 AM"},
        "planning_user_preference": "easy quarter",
        "an_unrelated_key": "preserve me",
    })

    streamlit_auth.clear_user_scoped_session()

    for leaked in (
        "user_id",
        "username",
        "authentication_status",
        "name",
        "email",
        "missing_details",
        "parsed_rows",
        "transcript_progress_snapshot",
        "planning_result",
        "enriched_courses",
        "_recommended_enrichment_fp",
        "course_schedule_map",
        "planning_user_preference",
    ):
        assert leaked not in stub_session_state, f"{leaked} survived logout"

    assert stub_session_state["an_unrelated_key"] == "preserve me"


def test_clear_user_scoped_session_is_safe_when_empty(stub_session_state):
    from auth import streamlit_auth

    streamlit_auth.clear_user_scoped_session()

    assert dict(stub_session_state) == {}
