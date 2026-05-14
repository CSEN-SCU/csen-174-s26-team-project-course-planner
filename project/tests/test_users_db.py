"""Tests for auth/users_db.py.

Behaviour pinned by these tests:

- Account creation succeeds for valid input and returns a positive id.
- Username and email uniqueness are enforced (raises UserAlreadyExistsError).
- Password hashes are bcrypt (start with $2 prefix); raw password is never
  recoverable from the row.
- verify_login returns True for the correct password, False for wrong
  passwords and unknown usernames.
- get_credentials_dict only exposes username/email/hash, not raw passwords,
  in the shape streamlit-authenticator expects.

Run with: cd project/course_planner && pytest tests/test_users_db.py -v
"""

from __future__ import annotations

import pytest

from auth import users_db


def test_create_user_returns_positive_id(db_path):
    user_id = users_db.create_user("alice", "alice@example.com", "correct horse battery", db_path=db_path)
    assert isinstance(user_id, int)
    assert user_id > 0


def test_password_is_stored_as_bcrypt_hash_not_plaintext(db_path):
    users_db.create_user("alice", "alice@example.com", "correct horse battery", db_path=db_path)

    user = users_db.get_user_by_username("alice", db_path=db_path)

    assert user is not None
    assert user["password_hash"].startswith("$2")
    assert "correct horse battery" not in user["password_hash"]


def test_duplicate_username_raises(db_path):
    users_db.create_user("alice", "alice@example.com", "correct horse battery", db_path=db_path)

    with pytest.raises(users_db.UserAlreadyExistsError):
        users_db.create_user("alice", "alice2@example.com", "another password", db_path=db_path)


def test_duplicate_email_raises(db_path):
    users_db.create_user("alice", "alice@example.com", "correct horse battery", db_path=db_path)

    with pytest.raises(users_db.UserAlreadyExistsError):
        users_db.create_user("alice2", "alice@example.com", "another password", db_path=db_path)


def test_verify_login_true_for_correct_password(db_path):
    users_db.create_user("alice", "alice@example.com", "correct horse battery", db_path=db_path)

    assert users_db.verify_login("alice", "correct horse battery", db_path=db_path) is True


def test_verify_login_false_for_wrong_password(db_path):
    users_db.create_user("alice", "alice@example.com", "correct horse battery", db_path=db_path)

    assert users_db.verify_login("alice", "wrong password", db_path=db_path) is False


def test_verify_login_false_for_unknown_user(db_path):
    assert users_db.verify_login("ghost", "anything goes", db_path=db_path) is False


def test_short_password_rejected(db_path):
    with pytest.raises(ValueError):
        users_db.create_user("alice", "alice@example.com", "short", db_path=db_path)


def test_invalid_email_rejected(db_path):
    with pytest.raises(ValueError):
        users_db.create_user("alice", "not-an-email", "correct horse battery", db_path=db_path)


def test_get_credentials_dict_shape_matches_streamlit_authenticator(db_path):
    users_db.create_user("alice", "alice@example.com", "correct horse battery", db_path=db_path)
    users_db.create_user("bob", "bob@example.com", "even longer password", db_path=db_path)

    creds = users_db.get_credentials_dict(db_path=db_path)

    assert set(creds.keys()) == {"usernames"}
    assert set(creds["usernames"].keys()) == {"alice", "bob"}
    alice = creds["usernames"]["alice"]
    assert set(alice.keys()) == {"name", "email", "password"}
    assert alice["email"] == "alice@example.com"
    assert alice["password"].startswith("$2")
    assert "correct horse battery" not in alice["password"]


def test_get_user_by_email_case_insensitive(db_path):
    users_db.create_user("alice", "alice@example.com", "correct horse battery", db_path=db_path)
    row = users_db.get_user_by_email("Alice@Example.com", db_path=db_path)
    assert row is not None
    assert row["username"] == "alice"


def test_get_user_by_email_unknown_returns_none(db_path):
    assert users_db.get_user_by_email("nobody@example.com", db_path=db_path) is None


def test_get_or_create_user_for_google_creates_then_returns_same(db_path):
    u1 = users_db.get_or_create_user_for_google(
        "newuser@example.com", "google-sub-12345", db_path=db_path
    )
    u2 = users_db.get_or_create_user_for_google(
        "NewUser@Example.com", "google-sub-12345", db_path=db_path
    )
    assert u1["id"] == u2["id"]
    assert u1["email"] == "newuser@example.com"
