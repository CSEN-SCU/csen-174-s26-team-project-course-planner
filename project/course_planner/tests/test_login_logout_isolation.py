"""Pseudo-e2e isolation: login -> plan -> logout -> next user sees nothing.

A full Streamlit AppTest run is awkward for streamlit-authenticator's
cookie flow (flagged in spec §11), so we drive the same code paths
directly and assert the contract:

1. User A logs in (we set session_state directly the way streamlit-authenticator
   would after a successful authenticate).
2. A runs the orchestrator -> a plan_outcome row is written for A.
3. We call `clear_user_scoped_session()` (the logout side-effect).
4. User B logs in. B's `My memory` listing must NOT contain any of A's rows.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from agents import memory_agent, orchestrator, planning_agent
from auth import streamlit_auth, users_db


@pytest.fixture()
def stub_session_state(monkeypatch):
    import streamlit as st

    fake: dict = {}
    monkeypatch.setattr(st, "session_state", fake)
    return fake


def _stub_planning(monkeypatch, recommend):
    captured: list[str] = []

    class _Models:
        def generate_content(self, model, contents, config):
            captured.append(contents)
            return SimpleNamespace(
                text=json.dumps(
                    {"recommended": recommend, "total_units": 8, "advice": "ok"}
                )
            )

    class _Client:
        models = _Models()

    monkeypatch.setattr(planning_agent, "_get_client", lambda: _Client())
    return captured


def test_two_users_do_not_share_memory_across_login_logout(
    db_path, stub_session_state, monkeypatch
):
    a = users_db.create_user("alice", "alice@example.com", "correct horse battery")
    b = users_db.create_user("bob", "bob@example.com", "another solid password")

    captured = _stub_planning(
        monkeypatch,
        [{"course": "COEN 146", "category": "Core", "units": 4, "reason": "core"}],
    )

    # --- Alice signs in ---
    stub_session_state.update(
        {
            "authentication_status": True,
            "username": "alice",
            "user_id": a,
        }
    )

    orchestrator.plan_for_user(
        a,
        [{"course": "COEN 146", "category": "Core", "units": 4}],
        "Alice prefers morning labs",
    )
    alice_rows = memory_agent.list_for_user(a)
    assert len(alice_rows) == 1
    assert "Alice prefers morning labs" in alice_rows[0]["content"]

    # Simulate the rest of main.py touching session_state after plan.
    stub_session_state["missing_details"] = [{"course": "COEN 146"}]
    stub_session_state["planning_result"] = {"recommended": []}

    # --- Alice logs out ---
    streamlit_auth.clear_user_scoped_session()
    assert "user_id" not in stub_session_state
    assert "missing_details" not in stub_session_state
    assert "planning_result" not in stub_session_state

    # --- Bob signs in ---
    stub_session_state.update(
        {
            "authentication_status": True,
            "username": "bob",
            "user_id": b,
        }
    )

    bob_rows = memory_agent.list_for_user(b)
    assert bob_rows == [], "Bob's memory must be empty - no leak from Alice"

    # Bob runs his own plan; Alice's row count must stay at 1.
    orchestrator.plan_for_user(
        b,
        [{"course": "COEN 174", "category": "Core", "units": 4}],
        "Bob prefers afternoons",
    )

    bob_rows_after = memory_agent.list_for_user(b)
    alice_rows_after = memory_agent.list_for_user(a)

    assert len(bob_rows_after) == 1
    assert "Bob prefers afternoons" in bob_rows_after[0]["content"]
    assert len(alice_rows_after) == 1
    assert "Alice prefers morning labs" in alice_rows_after[0]["content"]


def test_my_memory_panel_listing_is_user_scoped(db_path):
    a = users_db.create_user("alice", "alice@example.com", "correct horse battery")
    b = users_db.create_user("bob", "bob@example.com", "another solid password")

    memory_agent.write(a, "note", "Alice note 1")
    memory_agent.write(a, "note", "Alice note 2")
    memory_agent.write(b, "note", "Bob note 1")

    listed_for_alice = memory_agent.list_for_user(a)
    listed_for_bob = memory_agent.list_for_user(b)

    alice_contents = {row["content"] for row in listed_for_alice}
    bob_contents = {row["content"] for row in listed_for_bob}

    assert alice_contents == {"Alice note 1", "Alice note 2"}
    assert bob_contents == {"Bob note 1"}
