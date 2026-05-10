"""Per-user memory stored as one human-readable Markdown file per user.

Public surface (every function is scoped to a single ``user_id``):

- ``write(user_id, kind, content, meta=None)`` -> int
- ``retrieve(user_id, query, k=4)`` -> list[dict]
- ``list_for_user(user_id)`` -> list[dict]
- ``delete(user_id, item_id)`` -> bool
- ``delete_all_for_user(user_id)`` -> int
- ``embed(text)`` -> list[float]

Each user file lives under ``COURSE_PLANNER_MEMORY_DIR`` (default
``<app>/data/memory``). Entries are delimited blocks so the file stays
editable in a text editor; retrieval embeds each entry and ranks by
cosine distance to the query embedding (same ``embed()`` rules as before).

Isolation invariants (``tests/test_memory_isolation.py``):
- Only the file for ``user_id`` is read or written; other users' paths are never opened.
- Invalid ``user_id`` raises ``ValueError`` before any filesystem access.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from db.migrate import EMBEDDING_DIM

DEFAULT_TOP_K = int(os.environ.get("MEMORY_TOP_K", "4"))
GEMINI_EMBED_MODEL = os.environ.get("MEMORY_EMBED_MODEL", "text-embedding-004")

ALLOWED_KINDS = ("preference", "plan_outcome", "note")

_BLOCK_RE = re.compile(
    r"^<<<MEMORY (.+?)>>>\n(.*?)<<<END_MEMORY>>>\s*",
    re.MULTILINE | re.DOTALL,
)

_FILE_PREAMBLE = """# SCU Course Planner — saved memory

One entry per machine block below (delimiter lines are auto-generated).
You may edit the paragraph text inside a block; keep the JSON on the opening delimiter line valid.

"""


def _memory_root() -> Path:
    default = Path(__file__).resolve().parent.parent / "data" / "memory"
    p = Path(os.environ.get("COURSE_PLANNER_MEMORY_DIR", str(default)))
    p.mkdir(parents=True, exist_ok=True)
    return p


def _user_file(uid: int) -> Path:
    return _memory_root() / f"{uid}.md"


def _read_raw(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _parse_blocks(text: str) -> list[dict[str, Any]]:
    """Return list of {id, user_id, kind, created, meta, content} from file body."""
    out: list[dict[str, Any]] = []
    for m in _BLOCK_RE.finditer(text):
        try:
            header = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        body = m.group(2).strip("\n")
        if not isinstance(header, dict):
            continue
        out.append(
            {
                "id": int(header["id"]),
                "user_id": int(header["user_id"]),
                "kind": str(header["kind"]),
                "created": str(header.get("created") or ""),
                "meta": header.get("meta"),
                "content": body,
            }
        )
    return out


def _strip_preamble(text: str) -> str:
    """Keep only delimiter blocks (everything from first <<<MEMORY)."""
    idx = text.find("<<<MEMORY")
    if idx == -1:
        return ""
    return text[idx:].lstrip("\n")


def _serialize_block(
    item_id: int,
    uid: int,
    kind: str,
    created: str,
    meta: Optional[dict],
    content: str,
) -> str:
    header = {
        "id": item_id,
        "user_id": uid,
        "kind": kind,
        "created": created,
        "meta": meta,
    }
    line = json.dumps(header, ensure_ascii=False, separators=(",", ":"))
    return f"<<<MEMORY {line}>>>\n{content.rstrip()}\n<<<END_MEMORY>>>\n\n"


def _validate_user_id(user_id) -> int:
    if user_id is None:
        raise ValueError("memory_agent: user_id is required (got None)")
    try:
        uid = int(user_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("memory_agent: user_id must be int-like") from exc
    if uid <= 0:
        raise ValueError("memory_agent: user_id must be positive")
    return uid


def _hash_fallback_embed(text: str) -> list[float]:
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
    text = (text or "").strip()
    if not text:
        return [0.0] * EMBEDDING_DIM

    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return _hash_fallback_embed(text)

    try:
        from google import genai

        client = genai.Client(api_key=api_key)
        result = client.models.embed_content(model=GEMINI_EMBED_MODEL, contents=text)
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
            values = (values + [0.0] * EMBEDDING_DIM)[:EMBEDDING_DIM]
        return values
    except Exception:
        return _hash_fallback_embed(text)


def _cosine_distance(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 1.0
    sim = dot / (na * nb)
    return max(0.0, min(2.0, 1.0 - sim))


def write(
    user_id,
    kind: str,
    content: str,
    meta: Optional[dict] = None,
    *,
    db_path: Optional[str] = None,
) -> int:
    del db_path  # legacy kwarg from SQLite era; ignored.
    uid = _validate_user_id(user_id)
    if kind not in ALLOWED_KINDS:
        raise ValueError(f"memory_agent: kind must be one of {ALLOWED_KINDS}")
    if not content or not content.strip():
        raise ValueError("memory_agent: content cannot be empty")

    path = _user_file(uid)
    raw = _read_raw(path)
    body = _strip_preamble(raw)
    items = _parse_blocks(body)
    next_id = max((it["id"] for it in items), default=0) + 1
    created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    block = _serialize_block(next_id, uid, kind, created, meta, content.strip())
    new_text = _FILE_PREAMBLE + body + block
    _write_atomic(path, new_text)
    return next_id


def retrieve(
    user_id,
    query: str,
    k: int = DEFAULT_TOP_K,
    *,
    db_path: Optional[str] = None,
) -> list[dict]:
    del db_path
    uid = _validate_user_id(user_id)
    if k <= 0:
        return []
    if not (query or "").strip():
        return []

    path = _user_file(uid)
    raw = _read_raw(path)
    items = _parse_blocks(_strip_preamble(raw))
    if not items:
        return []

    qv = embed(query)
    scored: list[tuple[float, dict[str, Any]]] = []
    for it in items:
        if int(it["user_id"]) != uid:
            continue
        cv = embed(it["content"])
        dist = _cosine_distance(qv, cv)
        scored.append((dist, it))
    scored.sort(key=lambda x: x[0])

    rows: list[dict] = []
    for dist, it in scored[: int(k)]:
        rows.append(
            {
                "id": it["id"],
                "user_id": it["user_id"],
                "kind": it["kind"],
                "content": it["content"],
                "meta_json": json.dumps(it["meta"], ensure_ascii=False)
                if it.get("meta") is not None
                else None,
                "created_at": it["created"],
                "distance": dist,
            }
        )
    return rows


def list_for_user(
    user_id,
    *,
    db_path: Optional[str] = None,
) -> list[dict]:
    del db_path
    uid = _validate_user_id(user_id)
    path = _user_file(uid)
    raw = _read_raw(path)
    items = _parse_blocks(_strip_preamble(raw))
    items.sort(key=lambda x: x["id"], reverse=True)
    out: list[dict] = []
    for it in items:
        if int(it["user_id"]) != uid:
            continue
        out.append(
            {
                "id": it["id"],
                "user_id": uid,
                "kind": it["kind"],
                "content": it["content"],
                "meta_json": json.dumps(it["meta"], ensure_ascii=False)
                if it.get("meta") is not None
                else None,
                "created_at": it["created"],
            }
        )
    return out


def delete(
    user_id,
    item_id: int,
    *,
    db_path: Optional[str] = None,
) -> bool:
    del db_path
    uid = _validate_user_id(user_id)
    iid = int(item_id)
    path = _user_file(uid)
    raw = _read_raw(path)
    body = _strip_preamble(raw)
    items = _parse_blocks(body)
    kept = [it for it in items if int(it["id"]) != iid]
    if len(kept) == len(items):
        return False
    new_body = "".join(
        _serialize_block(
            it["id"],
            int(it["user_id"]),
            it["kind"],
            it["created"],
            it.get("meta"),
            it["content"],
        )
        for it in kept
    )
    _write_atomic(path, _FILE_PREAMBLE + new_body)
    return True


def delete_all_for_user(
    user_id,
    *,
    db_path: Optional[str] = None,
) -> int:
    del db_path
    uid = _validate_user_id(user_id)
    path = _user_file(uid)
    raw = _read_raw(path)
    n = len(_parse_blocks(_strip_preamble(raw)))
    if n == 0:
        return 0
    _write_atomic(path, _FILE_PREAMBLE)
    return n
