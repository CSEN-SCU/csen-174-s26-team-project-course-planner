"""User identity store for Google OAuth sign-in.

The module owns the SQLite ``users`` table used to scope planner memory and
other per-user data. Account authentication is handled by Google OAuth; this
store only records the stable local identity linked to a verified Google
account.

Public functions:

- `create_user(google_sub, email, *, db_path=None) -> int`
- `get_user_by_google_sub(google_sub, *, db_path=None) -> dict | None`
- `get_user_by_id(user_id, *, db_path=None) -> dict | None`
- `get_user_by_email(email, *, db_path=None) -> dict | None`
- `get_or_create_user_for_google(email, google_sub, *, db_path=None) -> dict`
- `delete_user_by_id(user_id, *, db_path=None) -> bool`

Errors:

- `UserAlreadyExistsError` if the Google subject or email already exists.
- `UserNotFoundError` from helpers that require the user to exist.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
from typing import Optional

from db.connection import close_conn, get_conn

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class UserAlreadyExistsError(Exception):
    """Raised when a Google subject or email is already taken."""


class UserNotFoundError(Exception):
    """Raised when a lookup expects a user but none exists."""


def stable_user_id(google_sub: str) -> int:
    """Deterministic positive int from Google ``sub`` (stable across deploys)."""
    normalized_sub = (google_sub or "").strip()
    if not normalized_sub:
        raise ValueError("Google account id is missing.")
    sub_hash = hashlib.sha256(normalized_sub.encode("utf-8")).digest()
    uid = int.from_bytes(sub_hash[:8], byteorder="big") & 0x7FFFFFFFFFFFFFFF
    return uid if uid else 1


def _validate_inputs(google_sub: str, email: str) -> None:
    if not isinstance(google_sub, str) or not google_sub.strip():
        raise ValueError("Google account id is missing.")
    if not _EMAIL_RE.match(email or ""):
        raise ValueError("Email must look like 'name@host.tld'.")


def create_user(
    google_sub: str,
    email: str,
    *,
    db_path: Optional[str] = None,
) -> int:
    """Insert a new OAuth-backed user; returns its id."""
    normalized_sub = google_sub.strip()
    _validate_inputs(normalized_sub, email)
    uid = stable_user_id(normalized_sub)

    conn = get_conn(db_path)
    try:
        try:
            conn.execute(
                "INSERT INTO users (id, google_sub, email) VALUES (?, ?, ?)",
                (uid, normalized_sub, email),
            )
            conn.commit()
        except sqlite3.IntegrityError as exc:
            raise UserAlreadyExistsError(
                "A user with that Google account or email already exists."
            ) from exc
        return uid
    finally:
        close_conn(conn)


def get_user_by_google_sub(
    google_sub: str,
    *,
    db_path: Optional[str] = None,
) -> Optional[dict]:
    if not isinstance(google_sub, str) or not google_sub.strip():
        return None
    conn = get_conn(db_path)
    try:
        row = conn.execute(
            "SELECT id, google_sub, email, created_at FROM users WHERE google_sub = ?",
            (google_sub.strip(),),
        ).fetchone()
        return dict(row) if row else None
    finally:
        close_conn(conn)


def get_user_by_id(
    user_id,
    *,
    db_path: Optional[str] = None,
) -> Optional[dict]:
    """Return the user row for this id, or None if no such user exists.

    Accepts any int-coercible value; non-numeric or non-positive input
    yields None rather than raising — the caller can then map "missing
    or invalid" to a single 401 response without leaking which case hit.
    """
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        return None
    if uid <= 0:
        return None
    conn = get_conn(db_path)
    try:
        row = conn.execute(
            "SELECT id, google_sub, email, created_at FROM users WHERE id = ?",
            (uid,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        close_conn(conn)


def get_user_by_email(
    email: str,
    *,
    db_path: Optional[str] = None,
) -> Optional[dict]:
    """Return the user row for this email, or None."""
    if not email or not isinstance(email, str):
        return None
    normalized = email.strip().lower()
    if not normalized:
        return None
    conn = get_conn(db_path)
    try:
        row = conn.execute(
            "SELECT id, google_sub, email, created_at FROM users WHERE lower(email) = ?",
            (normalized,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        close_conn(conn)


def _migrate_user_row_to_stable_id(
    existing: dict,
    *,
    db_path: Optional[str] = None,
) -> dict:
    """Move legacy auto-increment ids to stable ids and rename memory files."""
    from agents import memory_agent

    stable_id = stable_user_id(str(existing["google_sub"]))
    old_id = int(existing["id"])
    if old_id == stable_id:
        return existing

    memory_agent.migrate_user_storage(old_id, stable_id)

    conn = get_conn(db_path)
    try:
        conflict = conn.execute(
            "SELECT id, google_sub FROM users WHERE id = ?",
            (stable_id,),
        ).fetchone()
        if conflict is not None:
            if str(conflict["google_sub"]) == str(existing["google_sub"]):
                conn.execute("DELETE FROM users WHERE id = ?", (old_id,))
            else:
                raise RuntimeError(
                    "Cannot migrate user: stable id already assigned to another account."
                )
        else:
            conn.execute(
                "UPDATE users SET id = ? WHERE id = ?",
                (stable_id, old_id),
            )
        conn.commit()
    finally:
        close_conn(conn)

    migrated = get_user_by_id(stable_id, db_path=db_path)
    if migrated is None:
        raise RuntimeError("User migration failed.")
    return migrated


def get_or_create_user_for_google(
    email: str,
    google_sub: str,
    *,
    db_path: Optional[str] = None,
) -> dict:
    """Find user by Google subject or email, or create one for Google sign-in.

    Idempotent and TOCTOU-safe: if another callback races us and inserts the
    same identity between our reads and ``create_user``, we re-read the row
    instead of bubbling :class:`UserAlreadyExistsError` up to the user.

    Legacy rows created with auto-increment ids (1, 2, 3, …) are migrated to
    stable ids on every login so memory files no longer collide on serverless.
    """
    if not _EMAIL_RE.match((email or "").strip()):
        raise ValueError("Google account email is missing or invalid.")
    normalized_email = email.strip().lower()

    normalized_sub = (google_sub or "").strip()
    if not normalized_sub:
        raise ValueError("Google account id is missing.")

    existing = get_user_by_google_sub(normalized_sub, db_path=db_path)
    if existing is not None:
        return _migrate_user_row_to_stable_id(existing, db_path=db_path)

    existing = get_user_by_email(normalized_email, db_path=db_path)
    if existing is not None:
        return _migrate_user_row_to_stable_id(existing, db_path=db_path)

    try:
        create_user(normalized_sub, normalized_email, db_path=db_path)
    except UserAlreadyExistsError:
        # Concurrent callback inserted the same email or Google subject; re-read.
        existing = get_user_by_google_sub(normalized_sub, db_path=db_path)
        if existing is not None:
            return _migrate_user_row_to_stable_id(existing, db_path=db_path)
        existing = get_user_by_email(normalized_email, db_path=db_path)
        if existing is not None:
            return _migrate_user_row_to_stable_id(existing, db_path=db_path)
        raise
    user = get_user_by_google_sub(normalized_sub, db_path=db_path)
    if user is None:
        raise RuntimeError("User was created but could not be reloaded.")
    return user


def delete_user_by_id(
    user_id,
    *,
    db_path: Optional[str] = None,
) -> bool:
    """Delete the user row from SQLite. Returns False if id is invalid or missing."""
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        return False
    if uid <= 0:
        return False
    conn = get_conn(db_path)
    try:
        cur = conn.execute("DELETE FROM users WHERE id = ?", (uid,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        close_conn(conn)
