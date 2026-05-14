"""Rolling memory compaction keeps per-user Markdown under a byte budget.

After each ``write``, if total UTF-8 body size exceeds
``MEMORY_COMPACTION_TRIGGER_BYTES``, oldest entries (excluding the most
recent ``MEMORY_COMPACTION_PROTECT_RECENT`` by id) merge into one ``note``
with ``meta.auto_compaction`` so retrieval still sees one coherent block.
"""

from __future__ import annotations

import json

import pytest

from agents import memory_agent
from auth import users_db


def _body_bytes_for_user(uid: int) -> int:
    rows = memory_agent.list_for_user(uid)
    return sum(len(r["content"].encode("utf-8")) for r in rows)


@pytest.fixture()
def alice(db_path):
    return users_db.create_user(
        "alice", "alice@example.com", "correct horse battery", db_path=db_path
    )


def test_compaction_drops_total_bytes_below_trigger(monkeypatch, alice):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setenv("MEMORY_COMPACTION_TRIGGER_BYTES", "900")
    monkeypatch.setenv("MEMORY_COMPACTION_BATCH", "4")
    monkeypatch.setenv("MEMORY_COMPACTION_PROTECT_RECENT", "2")

    chunk = "m" * 120  # 120 bytes per note
    for i in range(14):
        memory_agent.write(alice, "preference", f"{i}:{chunk}")

    assert _body_bytes_for_user(alice) <= 900


def test_compaction_preserves_recent_rows_and_tags_summary(monkeypatch, alice):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setenv("MEMORY_COMPACTION_TRIGGER_BYTES", "900")
    monkeypatch.setenv("MEMORY_COMPACTION_BATCH", "4")
    monkeypatch.setenv("MEMORY_COMPACTION_PROTECT_RECENT", "2")

    pad = "p" * 110
    for i in range(14):
        memory_agent.write(alice, "preference", f"note-{i}-unique-marker-{pad}")

    rows = memory_agent.list_for_user(alice)
    kinds = {r["kind"] for r in rows}
    assert "preference" in kinds
    assert any(r["kind"] == "note" for r in rows)

    summary_rows = [r for r in rows if r["kind"] == "note" and r.get("meta_json")]
    assert summary_rows, "expected at least one compaction summary row"
    meta = json.loads(summary_rows[0]["meta_json"])
    assert meta.get("auto_compaction") is True
    assert "compacted_from_ids" in meta

    # Newest two raw preference strings should still exist as separate rows.
    assert any("note-13-unique-marker" in r["content"] for r in rows)
    assert any("note-12-unique-marker" in r["content"] for r in rows)
    assert _body_bytes_for_user(alice) <= 900
