"""Tests for auth/users_db.py.

Behaviour pinned by these tests:

- Account creation succeeds for valid OAuth identity input and returns a
  positive id.
- Google subject and email uniqueness are enforced (raises UserAlreadyExistsError).
- User rows only expose local identity fields.

Run with: cd project && pytest tests/test_users_db.py -v
"""

from __future__ import annotations

import pytest

from auth import users_db


def test_create_user_returns_positive_id(db_path):
    user_id = users_db.create_user("alice", "alice@example.com", db_path=db_path)
    assert isinstance(user_id, int)
    assert user_id > 0


def test_user_row_only_exposes_identity_fields(db_path):
    users_db.create_user("alice", "alice@example.com", db_path=db_path)

    user = users_db.get_user_by_google_sub("alice", db_path=db_path)

    assert user is not None
    assert set(user) == {"id", "google_sub", "email", "created_at"}


def test_duplicate_google_sub_raises(db_path):
    users_db.create_user("alice", "alice@example.com", db_path=db_path)

    with pytest.raises(users_db.UserAlreadyExistsError):
        users_db.create_user("alice", "alice2@example.com", db_path=db_path)


def test_duplicate_email_raises(db_path):
    users_db.create_user("alice", "alice@example.com", db_path=db_path)

    with pytest.raises(users_db.UserAlreadyExistsError):
        users_db.create_user("alice2", "alice@example.com", db_path=db_path)


def test_invalid_email_rejected(db_path):
    with pytest.raises(ValueError):
        users_db.create_user("alice", "not-an-email", db_path=db_path)


def test_get_user_by_email_case_insensitive(db_path):
    users_db.create_user("alice", "alice@example.com", db_path=db_path)
    row = users_db.get_user_by_email("Alice@Example.com", db_path=db_path)
    assert row is not None
    assert row["google_sub"] == "alice"


def test_get_user_by_email_unknown_returns_none(db_path):
    assert users_db.get_user_by_email("nobody@example.com", db_path=db_path) is None


def test_legacy_user_migrates_to_stable_id_on_login(db_path):
    """Auto-increment ids (1, 2, …) must not be reused after OAuth login."""
    import os
    from pathlib import Path

    from agents import memory_agent
    from auth import users_db

    mem_dir = Path(os.environ["COURSE_PLANNER_MEMORY_DIR"])

    conn_path = db_path
    from db.connection import close_conn, get_conn

    conn = get_conn(conn_path)
    try:
        conn.execute(
            "INSERT INTO users (id, google_sub, email) VALUES (?, ?, ?)",
            (1, "legacy-google-sub", "legacy@example.com"),
        )
        conn.commit()
    finally:
        close_conn(conn)

    memory_agent.write(1, "preference", "legacy user private note")

    user = users_db.get_or_create_user_for_google(
        "legacy@example.com",
        "legacy-google-sub",
        db_path=db_path,
    )
    stable = users_db.stable_user_id("legacy-google-sub")
    assert user["id"] == stable
    assert stable != 1
    assert not (mem_dir / "1.md").exists()
    rows = memory_agent.list_for_user(stable)
    assert any("legacy user private note" in r["content"] for r in rows)


def test_get_or_create_user_for_google_creates_then_returns_same(db_path):
    u1 = users_db.get_or_create_user_for_google(
        "newuser@example.com", "google-sub-12345", db_path=db_path
    )
    u2 = users_db.get_or_create_user_for_google(
        "NewUser@Example.com", "google-sub-12345", db_path=db_path
    )
    assert u1["id"] == u2["id"]
    assert u1["email"] == "newuser@example.com"


def test_local_login_helper_is_removed():
    assert not hasattr(users_db, "verify_" + "login")
