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

When total stored body bytes exceed ``MEMORY_COMPACTION_TRIGGER_BYTES``,
``write`` rewrites the file so the oldest eligible rows merge into one
``note`` (Gemini summary when a key is set, else excerpt join); the newest
``MEMORY_COMPACTION_PROTECT_RECENT`` rows are never merged away.
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
def _compaction_trigger_bytes() -> int:
    # Bumped from 64KB → 512KB.  A single parsed_rows JSON for a typical
    # SCU transcript is 30–80KB, which used to push the file over the old
    # 64KB threshold and trigger destructive shrinking of structured data.
    return int(os.environ.get("MEMORY_COMPACTION_TRIGGER_BYTES", "524288"))


def _compaction_batch() -> int:
    return max(2, int(os.environ.get("MEMORY_COMPACTION_BATCH", "8")))


def _compaction_protect_recent() -> int:
    return max(0, int(os.environ.get("MEMORY_COMPACTION_PROTECT_RECENT", "5")))


def _compaction_summary_max_chars() -> int:
    return int(os.environ.get("MEMORY_COMPACTION_SUMMARY_MAX_CHARS", "12000"))


GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

ALLOWED_KINDS = ("preference", "plan_outcome", "note", "academic_progress", "parsed_rows")

# Singleton kinds: only one entry per user; writing a new one replaces the old.
# Used for large structured payloads that always supersede older versions
# (transcript snapshots) so the file doesn't accumulate stale copies.
_SINGLETON_KINDS = frozenset(("academic_progress", "parsed_rows"))

# Never include these kinds in the text-summarization compaction batches —
# their JSON structure must remain intact so the frontend can parse them.
_NEVER_COMPACT_KINDS = frozenset(("academic_progress", "parsed_rows", "plan_outcome"))

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


def _total_body_bytes(items: list[dict[str, Any]]) -> int:
    return sum(len((it.get("content") or "").encode("utf-8")) for it in items)


def _fallback_compaction_summary(batch: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for it in batch:
        prefix = f"[{it['kind']}] "
        c = (it.get("content") or "").strip()
        if len(c) > 1200:
            c = c[:1200] + "…"
        parts.append(prefix + c)
    text = "\n\n".join(parts)
    cap = _compaction_summary_max_chars()
    if len(text) > cap:
        text = text[: cap - 1] + "…"
    return "Auto-merged older memory (excerpts):\n\n" + text


def _llm_compaction_summary(batch: list[dict[str, Any]]) -> Optional[str]:
    """Return a short merged paragraph when Gemini is available; else None."""
    try:
        from agents.gemini_client import get_genai_client

        client = get_genai_client(purpose="memory compaction")
    except Exception:
        return None
    lines = []
    for it in batch:
        body = (it.get("content") or "").strip()
        if len(body) > 2000:
            body = body[:2000] + "…"
        lines.append(f"- ({it.get('kind')}) {body}")
    bullet = "\n".join(lines)
    prompt = (
        "Condense the following personal course-planner memory notes into one "
        "concise paragraph (under 800 words). Preserve course codes, time/day "
        "preferences, and degree constraints. Do not invent facts.\n\nNotes:\n"
        f"{bullet}"
    )
    try:
        response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
        text = (getattr(response, "text", None) or "").strip()
        if not text:
            return None
        cap = _compaction_summary_max_chars()
        return text[:cap] if len(text) > cap else text
    except Exception:
        return None


def _is_auto_compaction_row(it: dict[str, Any]) -> bool:
    m = it.get("meta")
    return isinstance(m, dict) and m.get("auto_compaction") is True


def _compact_items(uid: int, items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], bool]:
    """Merge oldest eligible entries into one ``note`` until under byte threshold."""
    trigger = _compaction_trigger_bytes()
    batch = _compaction_batch()
    protect_cfg = _compaction_protect_recent()
    changed = False
    owned = [it for it in items if int(it["user_id"]) == uid]

    while _total_body_bytes(owned) > trigger:
        n = len(owned)
        if n < 2:
            break
        # Keep recent user-authored rows (exclude auto-compaction summaries) intact.
        authored = [it for it in owned if not _is_auto_compaction_row(it)]
        if len(authored) <= protect_cfg:
            protected_ids = {int(it["id"]) for it in authored}
        else:
            protect_n = min(protect_cfg, max(0, len(authored) - 1))
            by_id_desc = sorted(authored, key=lambda x: int(x["id"]), reverse=True)
            protected_ids = {int(it["id"]) for it in by_id_desc[:protect_n]}
        eligible = [
            it for it in owned
            if int(it["id"]) not in protected_ids
            and str(it.get("kind") or "") not in _NEVER_COMPACT_KINDS
        ]
        eligible.sort(key=lambda x: int(x["id"]))
        if len(eligible) < 2:
            break
        take = eligible[: min(batch, len(eligible))]
        take_ids = {int(it["id"]) for it in take}
        rest = [it for it in owned if int(it["id"]) not in take_ids]
        summary_body = _llm_compaction_summary(take) or _fallback_compaction_summary(take)
        new_id = max(int(it["id"]) for it in owned) + 1
        created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        new_item: dict[str, Any] = {
            "id": new_id,
            "user_id": uid,
            "kind": "note",
            "created": created,
            "meta": {"compacted_from_ids": sorted(take_ids), "auto_compaction": True},
            "content": summary_body,
        }
        owned = rest + [new_item]
        changed = True

    # Merging can leave a single large ``note`` still above the threshold; trim in place.
    owned, shrunk = _shrink_until_under_budget(owned, trigger)
    return owned, changed or shrunk


def _utf8_safe_prefix(enc: bytes, max_bytes: int) -> bytes:
    if max_bytes <= 0 or not enc:
        return b""
    if len(enc) <= max_bytes:
        return enc
    s = enc[:max_bytes]
    while s and (s[-1] & 0b1100_0000) == 0b1000_0000:
        s = s[:-1]
    return s


def _shrink_until_under_budget(
    items: list[dict[str, Any]], trigger: int
) -> tuple[list[dict[str, Any]], bool]:
    """Trim the longest UTF-8 bodies until total is at or below ``trigger``.

    Entries whose kind is in ``_NEVER_COMPACT_KINDS`` (academic_progress,
    parsed_rows, plan_outcome) are NEVER truncated — their content is
    structured JSON that must remain parseable for the frontend.  If only
    protected entries remain and they still exceed the budget, the file is
    left oversized rather than corrupting the data.
    """
    if _total_body_bytes(items) <= trigger:
        return items, False
    out = []
    for it in items:
        row = dict(it)
        if isinstance(row.get("meta"), dict):
            row["meta"] = dict(row["meta"])
        out.append(row)
    changed = False
    ellipsis = "…"
    ell_b = len(ellipsis.encode("utf-8"))
    for _ in range(5000):
        total = _total_body_bytes(out)
        if total <= trigger:
            break
        if not out:
            break
        # Only shrinkable (non-protected) entries are eligible
        eligible_idx = [
            i for i in range(len(out))
            if str(out[i].get("kind") or "") not in _NEVER_COMPACT_KINDS
        ]
        if not eligible_idx:
            break  # Nothing left to safely trim — file stays oversized
        idx = max(eligible_idx, key=lambda i: len((out[i].get("content") or "").encode("utf-8")))
        enc = (out[idx].get("content") or "").encode("utf-8")
        if len(enc) <= 1:
            break
        others = total - len(enc)
        room = max(1, trigger - others)
        prefix_b = max(0, room - ell_b)
        clipped = _utf8_safe_prefix(enc, prefix_b).decode("utf-8", "ignore").rstrip()
        out[idx]["content"] = (clipped + ellipsis) if clipped else ellipsis
        meta = out[idx].get("meta") if isinstance(out[idx].get("meta"), dict) else {}
        out[idx]["meta"] = {**meta, "truncated_to_budget": True}
        changed = True
    return out, changed


def _split_transcript_tail(raw: str) -> tuple[str, str]:
    """Split ``raw`` into (prefix before transcript section, tail from ``## Last Transcript`` onward)."""
    s = raw or ""
    idx = s.find("\n## Last Transcript")
    if idx != -1:
        return s[:idx], s[idx + 1 :].lstrip("\n")
    if s.startswith("## Last Transcript"):
        return "", s
    idx2 = s.find("## Last Transcript")
    if idx2 != -1:
        return s[:idx2], s[idx2:]
    return s, ""


def _rewrite_blocks(uid: int, items: list[dict[str, Any]]) -> None:
    path = _user_file(uid)
    raw = _read_raw(path)
    _, tr_tail = _split_transcript_tail(raw)
    ordered = sorted(items, key=lambda x: int(x["id"]))
    body = "".join(
        _serialize_block(
            int(it["id"]),
            int(it["user_id"]),
            str(it["kind"]),
            str(it.get("created") or ""),
            it.get("meta") if isinstance(it.get("meta"), dict) else None,
            str(it.get("content") or ""),
        )
        for it in ordered
    )
    suffix = ("\n\n" + tr_tail) if tr_tail else ""
    _write_atomic(path, _FILE_PREAMBLE + body + suffix)


def _maybe_compact_after_write(uid: int) -> None:
    path = _user_file(uid)
    raw = _read_raw(path)
    owned = [
        it
        for it in _parse_blocks(_strip_preamble(raw))
        if int(it["user_id"]) == uid
    ]
    if not owned:
        return
    compacted, changed = _compact_items(uid, owned)
    if changed:
        _rewrite_blocks(uid, compacted)


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
    prefix_before_tr, tr_tail = _split_transcript_tail(raw)
    body = _strip_preamble(prefix_before_tr)
    items = _parse_blocks(body)
    # Singleton kinds: drop any existing entry of the same kind for this user
    # so the new one fully replaces it (no accumulation, no compaction loss).
    if kind in _SINGLETON_KINDS:
        items = [
            it for it in items
            if not (int(it["user_id"]) == uid and str(it["kind"]) == kind)
        ]
    next_id = max((it["id"] for it in items), default=0) + 1
    created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    block = _serialize_block(next_id, uid, kind, created, meta, content.strip())
    new_core = "".join(
        _serialize_block(
            int(it["id"]),
            int(it["user_id"]),
            str(it["kind"]),
            str(it.get("created") or ""),
            it.get("meta") if isinstance(it.get("meta"), dict) else None,
            str(it.get("content") or ""),
        )
        for it in sorted(items, key=lambda x: int(x["id"]))
    ) + block
    suffix = ("\n\n" + tr_tail) if tr_tail else ""
    new_text = _FILE_PREAMBLE + new_core + suffix
    _write_atomic(path, new_text)
    _maybe_compact_after_write(uid)
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
    prefix_before_tr, tr_tail = _split_transcript_tail(raw)
    body = _strip_preamble(prefix_before_tr)
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
    suffix = ("\n\n" + tr_tail) if tr_tail else ""
    _write_atomic(path, _FILE_PREAMBLE + new_body + suffix)
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
    _, tr_tail = _split_transcript_tail(raw)
    suffix = ("\n\n" + tr_tail) if tr_tail else ""
    _write_atomic(path, _FILE_PREAMBLE.rstrip("\n") + suffix)
    return n


def save_last_transcript_snapshot(user_id, snapshot: dict[str, Any]) -> None:
    """Append or replace a ``## Last Transcript`` JSON section at the end of the user's memory .md file."""
    uid = _validate_user_id(user_id)
    path = _user_file(uid)
    raw = _read_raw(path)
    base, _ = _split_transcript_tail(raw)
    base = base.rstrip()
    blob = json.dumps(snapshot, ensure_ascii=False, default=str)
    appendix = f"\n\n## Last Transcript\n\n```json\n{blob}\n```\n"
    _write_atomic(path, base + appendix)


def load_last_transcript_snapshot(user_id) -> Optional[dict[str, Any]]:
    """Load transcript snapshot from ``## Last Transcript`` in the user's memory .md file."""
    uid = _validate_user_id(user_id)
    raw = _read_raw(_user_file(uid))
    _, tail = _split_transcript_tail(raw)
    if not tail.strip():
        return None
    m = re.search(r"```json\s*\n(.*)\n```", tail, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(1).strip())
    except json.JSONDecodeError:
        return None
