"""Memory cross-user isolation red line.

Locks down spec §6 invariant: every memory operation is scoped by
``user_id``; there is no public path that lets user B's query surface
user A's rows.

These tests use the deterministic hash-based fallback embedder (no
GEMINI_API_KEY in the test env) so they run offline and deterministically.
"""

from __future__ import annotations

import pytest

from agents import memory_agent
from auth import users_db


@pytest.fixture()
def two_users(db_path):
    a = users_db.create_user("alice", "alice@example.com", "correct horse battery", db_path=db_path)
    b = users_db.create_user("bob", "bob@example.com", "another solid password", db_path=db_path)
    return {"alice": a, "bob": b}


def test_retrieve_only_returns_rows_for_caller(two_users):
    a, b = two_users["alice"], two_users["bob"]

    memory_agent.write(a, "preference", "Alice prefers morning labs and quality professors")
    memory_agent.write(a, "preference", "Alice avoids Friday classes")
    memory_agent.write(a, "plan_outcome", "Alice last quarter took COEN 146, COEN 174")

    memory_agent.write(b, "preference", "Bob prefers afternoons and easy graders")
    memory_agent.write(b, "plan_outcome", "Bob last quarter took COEN 161, ELEN 153")

    bob_hits = memory_agent.retrieve(b, "preferences for next quarter", k=10)
    bob_ids = {row["id"] for row in bob_hits}
    bob_rows = memory_agent.list_for_user(b)
    bob_owned_ids = {row["id"] for row in bob_rows}

    assert bob_ids, "Bob's retrieval should at least return his own rows"
    assert bob_ids.issubset(bob_owned_ids), (
        f"Bob's retrieve leaked rows from another user: {bob_ids - bob_owned_ids}"
    )
    for row in bob_hits:
        assert row["user_id"] == b
        assert "Alice" not in row["content"]


def test_retrieve_with_none_user_id_raises():
    with pytest.raises(ValueError):
        memory_agent.retrieve(None, "any query", k=4)


def test_retrieve_with_zero_user_id_raises(db_path):
    with pytest.raises(ValueError):
        memory_agent.retrieve(0, "any query", k=4)


def test_write_with_none_user_id_raises():
    with pytest.raises(ValueError):
        memory_agent.write(None, "preference", "anything")


def test_list_for_user_only_returns_owner_rows(two_users):
    a, b = two_users["alice"], two_users["bob"]
    memory_agent.write(a, "preference", "Alice item 1")
    memory_agent.write(a, "preference", "Alice item 2")
    memory_agent.write(b, "preference", "Bob item 1")

    rows = memory_agent.list_for_user(b)

    assert len(rows) == 1
    assert rows[0]["user_id"] == b
    assert rows[0]["content"] == "Bob item 1"


def test_delete_refuses_to_remove_another_users_row(two_users):
    a, b = two_users["alice"], two_users["bob"]
    alice_item = memory_agent.write(a, "preference", "Alice secret note")

    bob_attempt = memory_agent.delete(b, alice_item)
    assert bob_attempt is False

    alice_rows = memory_agent.list_for_user(a)
    assert any(row["id"] == alice_item for row in alice_rows), (
        "Alice's row must survive Bob's delete attempt"
    )


def test_delete_all_for_user_does_not_touch_other_users(two_users):
    a, b = two_users["alice"], two_users["bob"]
    memory_agent.write(a, "preference", "Alice 1")
    memory_agent.write(a, "preference", "Alice 2")
    memory_agent.write(b, "preference", "Bob 1")
    memory_agent.write(b, "preference", "Bob 2")
    memory_agent.write(b, "preference", "Bob 3")

    deleted = memory_agent.delete_all_for_user(b)

    assert deleted == 3
    assert memory_agent.list_for_user(b) == []
    assert len(memory_agent.list_for_user(a)) == 2


def test_delete_clears_vec_row_too(two_users, db_path):
    """Spec §5: deleting from memory_items must also drop the vec0 row.

    SQLite foreign-key cascade does not propagate into virtual tables,
    so memory_agent.delete is responsible for keeping both stores in sync.
    """
    a = two_users["alice"]
    item_id = memory_agent.write(a, "preference", "Alice item to be deleted")

    from db.connection import get_conn, close_conn

    conn = get_conn(db_path)
    try:
        before = conn.execute(
            "SELECT COUNT(*) FROM memory_vec WHERE rowid = ?", (item_id,)
        ).fetchone()[0]
        assert before == 1
    finally:
        close_conn(conn)

    assert memory_agent.delete(a, item_id) is True

    conn = get_conn(db_path)
    try:
        after_items = conn.execute(
            "SELECT COUNT(*) FROM memory_items WHERE id = ?", (item_id,)
        ).fetchone()[0]
        after_vec = conn.execute(
            "SELECT COUNT(*) FROM memory_vec WHERE rowid = ?", (item_id,)
        ).fetchone()[0]
    finally:
        close_conn(conn)

    assert after_items == 0
    assert after_vec == 0


def test_disallowed_kind_rejected(two_users):
    a = two_users["alice"]
    with pytest.raises(ValueError):
        memory_agent.write(a, "totally_made_up_kind", "x")


def test_empty_content_rejected(two_users):
    a = two_users["alice"]
    with pytest.raises(ValueError):
        memory_agent.write(a, "preference", "   ")
