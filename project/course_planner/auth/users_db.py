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


def _stable_user_id(google_sub: str) -> int:
    """Return the stable positive SQLite id derived from Google's subject."""
    sub_hash = hashlib.sha256(google_sub.strip().encode("utf-8")).digest()
    uid = int.from_bytes(sub_hash[:8], byteorder="big") & 0x7FFFFFFFFFFFFFFF
    return uid or 1


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
    uid = _stable_user_id(normalized_sub)

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


def _migrate_existing_user_id(
    user: dict,
    *,
    db_path: Optional[str] = None,
) -> dict:
    """Move legacy sequential ids to the stable Google-sub-derived id."""
    old_uid = int(user["id"])
    google_sub = str(user["google_sub"])
    new_uid = _stable_user_id(google_sub)
    if old_uid == new_uid:
        return user

    conn = get_conn(db_path)
    try:
        collision = conn.execute(
            "SELECT id FROM users WHERE id = ? AND id != ?",
            (new_uid, old_uid),
        ).fetchone()
        if collision is not None:
            raise UserAlreadyExistsError("A user with that stable id already exists.")

        # Existing pre-hash rows may have memory_items children; SQLite cannot
        # update this INTEGER PRIMARY KEY with FK checks enabled because the
        # schema has no ON UPDATE CASCADE.
        conn.execute("PRAGMA foreign_keys = OFF")
        try:
            conn.execute("UPDATE users SET id = ? WHERE id = ?", (new_uid, old_uid))
            conn.execute(
                "UPDATE memory_items SET user_id = ? WHERE user_id = ?",
                (new_uid, old_uid),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.execute("PRAGMA foreign_keys = ON")
    finally:
        close_conn(conn)

    try:
        from agents.memory_agent import migrate_user_storage_id

        migrate_user_storage_id(old_uid, new_uid)
    except FileNotFoundError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("User id migrated but memory storage could not be moved.") from exc

    migrated = get_user_by_google_sub(google_sub, db_path=db_path)
    if migrated is None:
        raise RuntimeError("User id was migrated but could not be reloaded.")
    return migrated


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
    """
    if not _EMAIL_RE.match((email or "").strip()):
        raise ValueError("Google account email is missing or invalid.")
    normalized_email = email.strip().lower()

    normalized_sub = (google_sub or "").strip()
    if not normalized_sub:
        raise ValueError("Google account id is missing.")

    existing = get_user_by_google_sub(normalized_sub, db_path=db_path)
    if existing is not None:
        return _migrate_existing_user_id(existing, db_path=db_path)

    existing = get_user_by_email(normalized_email, db_path=db_path)
    if existing is not None:
        return _migrate_existing_user_id(existing, db_path=db_path)

    try:
        create_user(normalized_sub, normalized_email, db_path=db_path)
    except UserAlreadyExistsError:
        # Concurrent callback inserted the same email or Google subject; re-read.
        existing = get_user_by_google_sub(normalized_sub, db_path=db_path)
        if existing is not None:
            return existing
        existing = get_user_by_email(normalized_email, db_path=db_path)
        if existing is not None:
            return existing
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
