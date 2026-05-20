"""DELETE /auth/user/{user_id}/data removes memory file and SQLite user row."""

from __future__ import annotations

from agents import memory_agent
from auth import users_db


def test_delete_user_data_removes_memory_and_account(db_path, monkeypatch):
    monkeypatch.setattr(memory_agent, "_validate_user_id", lambda uid: int(uid))

    uid = users_db.create_user("alice_del", "alice_del@example.com", "password123")
    memory_agent.write(uid, "preference", "Alice prefers morning labs")
    memory_agent.write(uid, "plan_outcome", '{"recommended": []}')

    path = memory_agent._user_file(uid)
    assert path.is_file()
    assert users_db.get_user_by_id(uid) is not None

    memory_agent.purge_user_storage(uid)
    assert not path.is_file()
    assert users_db.delete_user_by_id(uid) is True

    assert users_db.get_user_by_id(uid) is None
    assert memory_agent.list_for_user(uid) == []


def test_delete_user_data_does_not_touch_other_users(db_path, monkeypatch):
    monkeypatch.setattr(memory_agent, "_validate_user_id", lambda uid: int(uid))

    alice = users_db.create_user("alice_keep", "alice_keep@example.com", "password123")
    bob = users_db.create_user("bob_drop", "bob_drop@example.com", "password123")
    memory_agent.write(alice, "preference", "Alice note")
    memory_agent.write(bob, "preference", "Bob note")

    memory_agent.purge_user_storage(bob)
    users_db.delete_user_by_id(bob)

    assert users_db.get_user_by_id(bob) is None
    assert users_db.get_user_by_id(alice) is not None
    assert len(memory_agent.list_for_user(alice)) == 1
