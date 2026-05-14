"""Memory singleton kinds + JSON-protection guarantees.

The user's transcript history vanished on re-login because:

  1. ``parsed_rows`` was not in ``ALLOWED_KINDS`` → every write raised
     ``ValueError`` (silently swallowed by ``except: pass`` upstream).

  2. Even after kindlist fix, auto-compaction merged old structured
     ``academic_progress`` / ``plan_outcome`` rows into a single text
     "note" row — destroying the JSON the frontend needs to parse.

  3. ``_shrink_until_under_budget`` chopped the longest content blindly,
     truncating a ``parsed_rows`` payload mid-JSON.

This test file pins all three guarantees:

  * ``parsed_rows`` is an allowed kind
  * singleton kinds replace prior versions in place
  * ``_NEVER_COMPACT_KINDS`` are excluded from both LLM compaction and
    byte-budget shrinking
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from agents import memory_agent


@pytest.fixture
def temp_memory_dir(monkeypatch):
    """Redirect memory storage to a fresh tempdir per test."""
    with tempfile.TemporaryDirectory() as d:
        monkeypatch.setenv("COURSE_PLANNER_MEMORY_DIR", d)
        yield Path(d)


@pytest.fixture(autouse=True)
def fake_validate_user_id(monkeypatch):
    """Bypass DB user existence check — these are pure file-I/O tests."""
    monkeypatch.setattr(memory_agent, "_validate_user_id", lambda uid: int(uid))


@pytest.fixture(autouse=True)
def disable_llm_compaction_summary(monkeypatch):
    """Force the fallback (non-LLM) compaction summarizer so tests are
    deterministic and don't try to call Gemini."""
    monkeypatch.setattr(memory_agent, "_llm_compaction_summary", lambda batch: None)


# ── kind allowlist ───────────────────────────────────────────────────────────


def test_parsed_rows_is_an_allowed_kind():
    """The kindlist regression that erased the user's transcript."""
    assert "parsed_rows" in memory_agent.ALLOWED_KINDS


def test_unknown_kind_still_rejected():
    """Allowlist must still gate truly invalid kinds — no silent acceptance."""
    with pytest.raises(ValueError):
        memory_agent.write(1, "definitely_not_a_real_kind", "x")


# ── singleton replacement ────────────────────────────────────────────────────


def _read_all(uid: int) -> list[dict]:
    raw = memory_agent._read_raw(memory_agent._user_file(uid))
    body, _ = memory_agent._split_transcript_tail(raw)
    body = memory_agent._strip_preamble(body)
    return memory_agent._parse_blocks(body)


def test_parsed_rows_singleton_replaces_prior_version(temp_memory_dir):
    """Writing parsed_rows twice keeps only the latest entry."""
    memory_agent.write(1, "parsed_rows", json.dumps([{"a": 1}]))
    memory_agent.write(1, "parsed_rows", json.dumps([{"b": 2}, {"c": 3}]))

    items = _read_all(1)
    parsed = [it for it in items if it["kind"] == "parsed_rows"]
    assert len(parsed) == 1, "exactly one parsed_rows entry must remain"
    assert json.loads(parsed[0]["content"]) == [{"b": 2}, {"c": 3}]


def test_academic_progress_singleton_replaces_prior_version(temp_memory_dir):
    memory_agent.write(1, "academic_progress", "[]")
    memory_agent.write(1, "academic_progress", json.dumps([{"requirement": "X"}]))

    items = _read_all(1)
    progress = [it for it in items if it["kind"] == "academic_progress"]
    assert len(progress) == 1
    assert json.loads(progress[0]["content"]) == [{"requirement": "X"}]


def test_singleton_only_applies_to_same_user(temp_memory_dir):
    memory_agent.write(1, "parsed_rows", json.dumps([{"u": 1}]))
    memory_agent.write(2, "parsed_rows", json.dumps([{"u": 2}]))
    # Both users keep their entries
    assert len([it for it in _read_all(1) if it["kind"] == "parsed_rows"]) == 1
    assert len([it for it in _read_all(2) if it["kind"] == "parsed_rows"]) == 1


def test_plan_outcome_is_not_singleton(temp_memory_dir):
    """plan_outcome accumulates one entry per session, not singleton."""
    memory_agent.write(1, "plan_outcome", '{"session": 1}')
    memory_agent.write(1, "plan_outcome", '{"session": 2}')
    plan_rows = [it for it in _read_all(1) if it["kind"] == "plan_outcome"]
    assert len(plan_rows) == 2


# ── compaction never eats structured JSON kinds ──────────────────────────────


def test_never_compact_kinds_constant_is_set_correctly():
    nc = memory_agent._NEVER_COMPACT_KINDS
    assert "parsed_rows" in nc
    assert "academic_progress" in nc
    assert "plan_outcome" in nc


def test_compact_items_skips_protected_kinds(monkeypatch):
    """When _compact_items is forced to run, it must NOT merge any
    structured-JSON kind into a text note."""
    # Force an aggressive trigger so compaction definitely fires
    monkeypatch.setattr(memory_agent, "_compaction_trigger_bytes", lambda: 1)
    monkeypatch.setattr(memory_agent, "_compaction_protect_recent", lambda: 0)
    monkeypatch.setattr(memory_agent, "_compaction_batch", lambda: 8)

    items = [
        {"id": 1, "user_id": 1, "kind": "note", "created": "2026-01-01T00:00:00Z",
         "meta": None, "content": "A" * 200},
        {"id": 2, "user_id": 1, "kind": "note", "created": "2026-01-02T00:00:00Z",
         "meta": None, "content": "B" * 200},
        {"id": 3, "user_id": 1, "kind": "academic_progress", "created": "2026-01-03T00:00:00Z",
         "meta": None, "content": '[{"requirement":"X"}]' * 5},
        {"id": 4, "user_id": 1, "kind": "parsed_rows", "created": "2026-01-04T00:00:00Z",
         "meta": None, "content": '[{"course":"CSEN 122"}]' * 5},
    ]
    new_items, changed = memory_agent._compact_items(1, items)

    # The two notes may have been merged; protected kinds must remain intact.
    kept = {(it["id"], it["kind"]): it for it in new_items}
    ap = next(it for it in new_items if it["kind"] == "academic_progress")
    pr = next(it for it in new_items if it["kind"] == "parsed_rows")
    assert ap["content"] == '[{"requirement":"X"}]' * 5
    assert pr["content"] == '[{"course":"CSEN 122"}]' * 5


def test_shrink_does_not_truncate_protected_json(monkeypatch):
    """_shrink_until_under_budget must leave structured JSON intact even
    when nothing else can be shrunk further."""
    big_json = '[' + ('{"a":1},' * 200) + '{"a":1}]'  # ~2KB of JSON
    items = [
        {"id": 1, "user_id": 1, "kind": "parsed_rows", "created": "2026-01-01T00:00:00Z",
         "meta": None, "content": big_json},
    ]
    # Trigger budget is 100 bytes — way smaller than the JSON
    new_items, changed = memory_agent._shrink_until_under_budget(items, trigger=100)
    parsed = next(it for it in new_items if it["kind"] == "parsed_rows")
    # JSON must remain parseable (not truncated mid-token)
    assert parsed["content"] == big_json
    assert json.loads(parsed["content"]) is not None


def test_shrink_truncates_unprotected_notes(monkeypatch):
    """The shrink mechanism still works for non-protected kinds."""
    items = [
        {"id": 1, "user_id": 1, "kind": "note", "created": "2026-01-01T00:00:00Z",
         "meta": None, "content": "X" * 5000},
    ]
    new_items, changed = memory_agent._shrink_until_under_budget(items, trigger=500)
    assert changed
    note = next(it for it in new_items if it["kind"] == "note")
    assert len(note["content"].encode("utf-8")) <= 500 + 10  # ellipsis fudge
    assert note["meta"]["truncated_to_budget"] is True


# ── compaction trigger default raised ────────────────────────────────────────


def test_compaction_trigger_default_at_least_256kb():
    """The default byte trigger was raised from 64KB → 512KB to comfortably
    fit a typical parsed_rows blob without pressuring compaction.

    Test asserts it stays ≥ 256KB so a future "let's be conservative"
    revert doesn't reintroduce the truncation bug.
    """
    original = os.environ.pop("MEMORY_COMPACTION_TRIGGER_BYTES", None)
    try:
        assert memory_agent._compaction_trigger_bytes() >= 256 * 1024
    finally:
        if original is not None:
            os.environ["MEMORY_COMPACTION_TRIGGER_BYTES"] = original


def test_compaction_trigger_env_override_still_works(monkeypatch):
    """Env var override still wins, for tests that want aggressive compaction."""
    monkeypatch.setenv("MEMORY_COMPACTION_TRIGGER_BYTES", "1024")
    assert memory_agent._compaction_trigger_bytes() == 1024
