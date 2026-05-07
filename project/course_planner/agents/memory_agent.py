"""Per-user RAG memory store backed by SQLite + sqlite-vec.

Public surface (every function is scoped to a single ``user_id`` to make
cross-user leakage impossible by construction):

- ``write(user_id, kind, content, meta=None)`` -> int
- ``retrieve(user_id, query, k=4)`` -> list[dict]
- ``list_for_user(user_id)`` -> list[dict]
- ``delete(user_id, item_id)`` -> bool
- ``delete_all_for_user(user_id)`` -> int
- ``embed(text)`` -> list[float]                   (Gemini text-embedding-004)

Embedding contract:
- Vector dim is ``EMBEDDING_DIM`` (default 768).
- If the Gemini API is unavailable, the module falls back to a
  deterministic hash-based pseudo-embedding so writes never block the
  user-facing flow. This is *only* a graceful fallback for development;
  production use should keep ``GEMINI_API_KEY`` set so retrieval quality
  is meaningful.

Isolation invariants (locked by ``tests/test_memory_isolation.py``):
- Every retrieval/list/delete query carries ``WHERE user_id = ?``.
- Calls with ``user_id=None`` (or non-positive int) raise ``ValueError``
  *before* touching the database.
"""

from __future__ import annotations

import hashlib
import json
import os
import struct
from typing import Iterable, Optional

from db.connection import close_conn, get_conn
from db.migrate import EMBEDDING_DIM

# -- public knobs ------------------------------------------------------------

DEFAULT_TOP_K = int(os.environ.get("MEMORY_TOP_K", "4"))
GEMINI_EMBED_MODEL = os.environ.get("MEMORY_EMBED_MODEL", "text-embedding-004")

ALLOWED_KINDS = ("preference", "plan_outcome", "note")


# -- helpers -----------------------------------------------------------------


def _validate_user_id(user_id) -> int:
    """Reject missing or non-positive user ids before any DB call."""
    if user_id is None:
        raise ValueError("memory_agent: user_id is required (got None)")
    try:
        uid = int(user_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("memory_agent: user_id must be int-like") from exc
    if uid <= 0:
        raise ValueError("memory_agent: user_id must be positive")
    return uid


def _serialize_vec(vec: Iterable[float]) -> bytes:
    """sqlite-vec accepts bytes of packed little-endian float32."""
    floats = [float(x) for x in vec]
    if len(floats) != EMBEDDING_DIM:
        raise ValueError(
            f"memory_agent: expected {EMBEDDING_DIM} dims, got {len(floats)}"
        )
    return struct.pack(f"{EMBEDDING_DIM}f", *floats)


def _hash_fallback_embed(text: str) -> list[float]:
    """Deterministic pseudo-embedding so writes never fail when Gemini is down.

    Uses repeated SHA-256 to stretch to the required dim, mapping each byte
    to ``[-1, 1]``. Quality is poor on purpose; it preserves the *interface*
    so the rest of the pipeline keeps working.
    """
    out: list[float] = []
    counter = 0
    seed = (text or "").encode("utf-8")
    while len(out) < EMBEDDING_DIM:
        h = hashlib.sha256(seed + counter.to_bytes(4, "big")).digest()
        for b in h:
            out.append((b - 127.5) / 127.5)
            if len(out) >= EMBEDDING_DIM:
                break
        counter += 1
    return out[:EMBEDDING_DIM]


def embed(text: str) -> list[float]:
    """Embed ``text`` via Gemini, falling back to a deterministic hash vector.

    The fallback path lets the prototype run without ``GEMINI_API_KEY`` and
    keeps the unit tests fast/offline.
    """
    text = (text or "").strip()
    if not text:
        return [0.0] * EMBEDDING_DIM

    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return _hash_fallback_embed(text)

    try:
        from google import genai  # local import keeps tests offline-safe

        client = genai.Client(api_key=api_key)
        result = client.models.embed_content(model=GEMINI_EMBED_MODEL, contents=text)
        # google-genai shapes: result.embeddings is a list[ContentEmbedding]
        # or a single ContentEmbedding with `.values: list[float]`.
        embeddings = getattr(result, "embeddings", None)
        if embeddings:
            first = embeddings[0]
            values = getattr(first, "values", None) or list(first)
        else:
            values = getattr(getattr(result, "embedding", None), "values", None)
        if not values:
            return _hash_fallback_embed(text)
        values = [float(v) for v in values]
        if len(values) != EMBEDDING_DIM:
            # Pad or truncate to the configured dim so we never break the schema.
            values = (values + [0.0] * EMBEDDING_DIM)[:EMBEDDING_DIM]
        return values
    except Exception:
        return _hash_fallback_embed(text)


# -- write -------------------------------------------------------------------


def write(
    user_id,
    kind: str,
    content: str,
    meta: Optional[dict] = None,
    *,
    db_path: Optional[str] = None,
) -> int:
    """Persist a memory item + its embedding. Returns the new item id."""
    uid = _validate_user_id(user_id)
    if kind not in ALLOWED_KINDS:
        raise ValueError(f"memory_agent: kind must be one of {ALLOWED_KINDS}")
    if not content or not content.strip():
        raise ValueError("memory_agent: content cannot be empty")

    meta_json = json.dumps(meta, ensure_ascii=False) if meta else None
    vec = _serialize_vec(embed(content))

    conn = get_conn(db_path)
    try:
        cur = conn.execute(
            "INSERT INTO memory_items (user_id, kind, content, meta_json) VALUES (?, ?, ?, ?)",
            (uid, kind, content, meta_json),
        )
        item_id = int(cur.lastrowid)
        conn.execute(
            "INSERT INTO memory_vec (rowid, embedding) VALUES (?, ?)",
            (item_id, vec),
        )
        conn.commit()
        return item_id
    finally:
        close_conn(conn)


# -- retrieve ----------------------------------------------------------------


def retrieve(
    user_id,
    query: str,
    k: int = DEFAULT_TOP_K,
    *,
    db_path: Optional[str] = None,
) -> list[dict]:
    """Return up to ``k`` memory rows for ``user_id`` ranked by vector closeness.

    The retrieval SQL always carries ``WHERE m.user_id = :uid``; there is
    no public path that bypasses this filter.
    """
    uid = _validate_user_id(user_id)
    if k <= 0:
        return []
    if not (query or "").strip():
        return []

    vec = _serialize_vec(embed(query))

    conn = get_conn(db_path)
    try:
        # We over-fetch from vec0 (which is per-row global, not per-user) and
        # then inner-join + filter by user_id. The user_id filter is the red
        # line; do not remove it.
        rows = conn.execute(
            """
            SELECT m.id        AS id,
                   m.user_id   AS user_id,
                   m.kind      AS kind,
                   m.content   AS content,
                   m.meta_json AS meta_json,
                   m.created_at AS created_at,
                   v.distance  AS distance
            FROM memory_vec v
            JOIN memory_items m ON m.id = v.rowid
            WHERE v.embedding MATCH :vec
              AND k = :over_k
              AND m.user_id = :uid
            ORDER BY v.distance ASC
            LIMIT :k
            """,
            {"vec": vec, "uid": uid, "k": int(k), "over_k": int(k) * 8 + 32},
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        close_conn(conn)


# -- list / delete -----------------------------------------------------------


def list_for_user(
    user_id,
    *,
    db_path: Optional[str] = None,
) -> list[dict]:
    """Return all memory rows for the user, newest first (sidebar UI uses this)."""
    uid = _validate_user_id(user_id)
    conn = get_conn(db_path)
    try:
        rows = conn.execute(
            "SELECT id, user_id, kind, content, meta_json, created_at "
            "FROM memory_items WHERE user_id = ? ORDER BY id DESC",
            (uid,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        close_conn(conn)


def delete(
    user_id,
    item_id: int,
    *,
    db_path: Optional[str] = None,
) -> bool:
    """Delete one memory item *only* if it belongs to ``user_id``.

    Returns True if a row was deleted, False otherwise.
    """
    uid = _validate_user_id(user_id)
    iid = int(item_id)
    conn = get_conn(db_path)
    try:
        cur = conn.execute(
            "DELETE FROM memory_items WHERE id = ? AND user_id = ?",
            (iid, uid),
        )
        deleted = cur.rowcount > 0
        # FK cascade does not propagate into the vec0 virtual table, so we
        # delete the vec row explicitly to keep the two stores in sync.
        if deleted:
            conn.execute("DELETE FROM memory_vec WHERE rowid = ?", (iid,))
        conn.commit()
        return deleted
    finally:
        close_conn(conn)


def delete_all_for_user(
    user_id,
    *,
    db_path: Optional[str] = None,
) -> int:
    """Delete every memory row for the user. Returns count deleted."""
    uid = _validate_user_id(user_id)
    conn = get_conn(db_path)
    try:
        ids = [
            row["id"]
            for row in conn.execute(
                "SELECT id FROM memory_items WHERE user_id = ?", (uid,)
            ).fetchall()
        ]
        if not ids:
            return 0
        placeholders = ",".join("?" * len(ids))
        conn.execute(
            f"DELETE FROM memory_items WHERE user_id = ? AND id IN ({placeholders})",
            (uid, *ids),
        )
        conn.execute(
            f"DELETE FROM memory_vec WHERE rowid IN ({placeholders})",
            tuple(ids),
        )
        conn.commit()
        return len(ids)
    finally:
        close_conn(conn)
