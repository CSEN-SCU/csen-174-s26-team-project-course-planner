"""User CRUD and credentials helpers.

Passwords are hashed with bcrypt (cost >= 12). The module exposes a small
surface so that `streamlit_authenticator.Authenticate` can be fed a
credentials dict pulled from SQLite, while tests can drive the same
functions directly.

Public functions:

- `create_user(username, email, password, *, db_path=None) -> int`
- `verify_login(username, password, *, db_path=None) -> bool`
- `get_user_by_username(username, *, db_path=None) -> dict | None`
- `get_credentials_dict(*, db_path=None) -> dict`

Errors:

- `UserAlreadyExistsError` if the username or email already exists.
- `UserNotFoundError` from helpers that require the user to exist.
"""

from __future__ import annotations

import re
import sqlite3
from typing import Optional

import bcrypt

from db.connection import close_conn, get_conn

BCRYPT_COST = 12
MIN_PASSWORD_LENGTH = 8
_USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# A valid bcrypt hash of the string "dummy" used as a constant-time decoy when
# the username does not exist. Avoids leaking existence via response timing.
_DUMMY_HASH = bcrypt.hashpw(b"dummy", bcrypt.gensalt(rounds=BCRYPT_COST))


class UserAlreadyExistsError(Exception):
    """Raised when a username or email is already taken."""


class UserNotFoundError(Exception):
    """Raised when a lookup expects a user but none exists."""


def _validate_inputs(username: str, email: str, password: str) -> None:
    if not _USERNAME_RE.match(username or ""):
        raise ValueError(
            "Username must be 3-32 chars: letters, digits, dot, underscore, or hyphen."
        )
    if not _EMAIL_RE.match(email or ""):
        raise ValueError("Email must look like 'name@host.tld'.")
    if not isinstance(password, str) or len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")


def _hash_password(password: str) -> str:
    salt = bcrypt.gensalt(rounds=BCRYPT_COST)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def _verify_password(password: str, stored_hash: str) -> bool:
    if not stored_hash or not isinstance(stored_hash, str):
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_user(
    username: str,
    email: str,
    password: str,
    *,
    db_path: Optional[str] = None,
) -> int:
    """Insert a new user; returns its id. Raises if name/email taken."""
    _validate_inputs(username, email, password)
    pw_hash = _hash_password(password)
    conn = get_conn(db_path)
    try:
        try:
            cur = conn.execute(
                "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
                (username, email, pw_hash),
            )
            conn.commit()
        except sqlite3.IntegrityError as exc:
            raise UserAlreadyExistsError(
                "A user with that username or email already exists."
            ) from exc
        return int(cur.lastrowid)
    finally:
        close_conn(conn)


def get_user_by_username(
    username: str,
    *,
    db_path: Optional[str] = None,
) -> Optional[dict]:
    conn = get_conn(db_path)
    try:
        row = conn.execute(
            "SELECT id, username, email, password_hash, created_at FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        close_conn(conn)


def verify_login(
    username: str,
    password: str,
    *,
    db_path: Optional[str] = None,
) -> bool:
    user = get_user_by_username(username, db_path=db_path)
    if user is None:
        # Constant-time decoy so unknown-username does not return faster than
        # known-username-wrong-password (mitigates username enumeration).
        bcrypt.checkpw(b"x", _DUMMY_HASH)
        return False
    return _verify_password(password, user["password_hash"])


def get_credentials_dict(*, db_path: Optional[str] = None) -> dict:
    """Build the credentials dict expected by `streamlit_authenticator`.

    Each user becomes:
        {
          'name':     <username>,
          'email':    <email>,
          'password': <bcrypt hash>,
        }
    The library accepts pre-hashed bcrypt strings.
    """
    conn = get_conn(db_path)
    try:
        rows = conn.execute(
            "SELECT username, email, password_hash FROM users"
        ).fetchall()
    finally:
        close_conn(conn)
    usernames: dict[str, dict] = {}
    for row in rows:
        usernames[row["username"]] = {
            "name": row["username"],
            "email": row["email"],
            "password": row["password_hash"],
        }
    return {"usernames": usernames}
