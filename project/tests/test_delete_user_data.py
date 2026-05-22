"""DELETE /auth/user/{user_id}/data removes memory file and SQLite user row."""

from __future__ import annotations

import sys
from pathlib import Path

_API_DIR = Path(__file__).resolve().parents[1] / "api"
sys.path.insert(0, str(_API_DIR))

from agents import memory_agent
from auth import users_db
from fastapi.testclient import TestClient

import main


def test_delete_user_data_removes_memory_and_account(db_path, monkeypatch):
    monkeypatch.setattr(memory_agent, "_validate_user_id", lambda uid: int(uid))

    uid = users_db.create_user("alice_del", "alice_del@example.com")
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

    alice = users_db.create_user("alice_keep", "alice_keep@example.com")
    bob = users_db.create_user("bob_drop", "bob_drop@example.com")
    memory_agent.write(alice, "preference", "Alice note")
    memory_agent.write(bob, "preference", "Bob note")

    memory_agent.purge_user_storage(bob)
    users_db.delete_user_by_id(bob)

    assert users_db.get_user_by_id(bob) is None
    assert users_db.get_user_by_id(alice) is not None
    assert len(memory_agent.list_for_user(alice)) == 1


def test_delete_user_data_api_clears_orphan_memory(db_path, monkeypatch):
    """Stale session: memory file exists but SQLite user row is gone → still 200 (sign-out)."""
    monkeypatch.setattr(memory_agent, "_validate_user_id", lambda uid: int(uid))

    uid = 4242
    memory_agent.write(uid, "preference", "orphan note")
    assert memory_agent._user_file(uid).is_file()

    with TestClient(main.app) as client:
        res = client.delete(f"/api/auth/user/{uid}/data")

    assert res.status_code == 200
    assert res.json().get("success") is True
    assert not memory_agent._user_file(uid).is_file()


def test_delete_user_data_api_full_account(db_path, monkeypatch):
    monkeypatch.setattr(memory_agent, "_validate_user_id", lambda uid: int(uid))

    uid = users_db.create_user("del_api", "del_api@example.com")
    memory_agent.write(uid, "preference", "note")

    with TestClient(main.app) as client:
        res = client.delete(f"/api/auth/user/{uid}/data")

    assert res.status_code == 200
    assert users_db.get_user_by_id(uid) is None
