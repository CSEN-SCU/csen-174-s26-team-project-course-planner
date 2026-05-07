"""orchestrator.plan_for_user wires retrieval -> prompt prefix -> write-back.

Verifies the spec §6 contract:
- Retrieved snippets are injected at the *top* of the prompt as
  "BACKGROUND CONTEXT" (history, not current instructions).
- Prompt prefix never exceeds MEMORY_INJECT_CHAR_BUDGET.
- Empty retrieval -> no header at all (no orphan "BACKGROUND CONTEXT:").
- After a successful plan, a `plan_outcome` row is persisted for the
  caller's user_id (best-effort write-back).

Tests stub the Gemini client so we never hit the network; they also
relies on the deterministic hash-based fallback embedder.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from agents import memory_agent, orchestrator, planning_agent
from auth import users_db


def _stub_client(captured_prompts: list[str], reply: dict):
    import json as _json

    class _StubModels:
        def generate_content(self, model, contents, config):  # noqa: D401
            captured_prompts.append(contents)
            return SimpleNamespace(text=_json.dumps(reply))

    class _StubClient:
        models = _StubModels()

    return _StubClient()


@pytest.fixture()
def alice(db_path):
    return users_db.create_user(
        "alice", "alice@example.com", "correct horse battery", db_path=db_path
    )


@pytest.fixture()
def reply():
    return {
        "recommended": [
            {"course": "COEN 146", "category": "Core", "units": 4, "reason": "core net"},
            {"course": "COEN 174", "category": "Core", "units": 4, "reason": "team SE"},
        ],
        "total_units": 8,
        "advice": "Take core first.",
    }


def _patch_client(monkeypatch, captured_prompts, reply):
    stub = _stub_client(captured_prompts, reply)
    monkeypatch.setattr(planning_agent, "_get_client", lambda: stub)


def test_inject_retrieved_snippets_into_prompt_prefix(monkeypatch, alice, reply):
    memory_agent.write(alice, "preference", "Alice prefers no classes before 9am, quality over difficulty")
    memory_agent.write(alice, "plan_outcome", "Last quarter Alice took COEN 146 with prof X, total_units=12")

    captured: list[str] = []
    _patch_client(monkeypatch, captured, reply)

    out = orchestrator.plan_for_user(
        alice,
        [{"course": "COEN 174", "category": "Core", "units": 4}],
        "easy quarter, prefer mornings",
    )

    assert out["total_units"] == 8
    assert len(captured) == 1
    prompt = captured[0]
    assert "BACKGROUND CONTEXT" in prompt
    assert prompt.index("BACKGROUND CONTEXT") < prompt.index("STUDENT REQUIREMENTS")
    assert "Alice prefers no classes" in prompt or "Last quarter Alice took" in prompt


def test_prompt_prefix_respects_char_budget(monkeypatch, alice, reply):
    """With many medium snippets, the assembled block stays under budget."""
    medium = "x" * 400  # several of these together exceed the 1500 char budget
    for i in range(10):
        memory_agent.write(alice, "preference", f"{i}: {medium}")

    captured: list[str] = []
    _patch_client(monkeypatch, captured, reply)

    orchestrator.plan_for_user(
        alice,
        [{"course": "COEN 174", "category": "Core", "units": 4}],
        "anything",
    )

    prompt = captured[0]
    header = "=== BACKGROUND CONTEXT"
    assert header in prompt
    head_idx = prompt.index(header)
    body_end = prompt.index("STUDENT REQUIREMENTS")
    prefix = prompt[head_idx:body_end]
    assert len(prefix) <= planning_agent.MEMORY_INJECT_CHAR_BUDGET, (
        f"Memory prefix is {len(prefix)} chars, budget {planning_agent.MEMORY_INJECT_CHAR_BUDGET}"
    )


def test_oversized_single_snippet_drops_block_gracefully(monkeypatch, alice, reply):
    """If even one snippet alone exceeds the budget, drop the whole header
    rather than emit an orphan 'BACKGROUND CONTEXT' label.
    """
    too_big = "y" * (planning_agent.MEMORY_INJECT_CHAR_BUDGET + 200)
    memory_agent.write(alice, "preference", too_big)

    captured: list[str] = []
    _patch_client(monkeypatch, captured, reply)

    orchestrator.plan_for_user(
        alice,
        [{"course": "COEN 174", "category": "Core", "units": 4}],
        "anything",
    )

    prompt = captured[0]
    assert "BACKGROUND CONTEXT" not in prompt


def test_no_injection_block_when_no_memory(monkeypatch, alice, reply):
    captured: list[str] = []
    _patch_client(monkeypatch, captured, reply)

    orchestrator.plan_for_user(
        alice,
        [{"course": "COEN 174", "category": "Core", "units": 4}],
        "first time planning",
    )

    prompt = captured[0]
    assert "BACKGROUND CONTEXT" not in prompt, (
        "Prompt must not include an empty memory header when retrieval is empty"
    )
    assert prompt.lstrip().startswith("=== STUDENT REQUIREMENTS")


def test_plan_for_user_writes_back_summary(monkeypatch, alice, reply):
    captured: list[str] = []
    _patch_client(monkeypatch, captured, reply)

    before = len(memory_agent.list_for_user(alice))

    orchestrator.plan_for_user(
        alice,
        [{"course": "COEN 174", "category": "Core", "units": 4}],
        "easy quarter, prefer mornings",
    )

    after = memory_agent.list_for_user(alice)
    assert len(after) == before + 1
    new_row = after[0]
    assert new_row["kind"] == "plan_outcome"
    assert "PREF:" in new_row["content"]
    assert "GAP:" in new_row["content"]
    assert "PLAN:" in new_row["content"]
    assert "COEN 146" in new_row["content"]
    assert "total_units=8" in new_row["content"]


def test_plan_for_user_requires_user_id(monkeypatch, reply):
    captured: list[str] = []
    _patch_client(monkeypatch, captured, reply)
    with pytest.raises(ValueError):
        orchestrator.plan_for_user(None, [{"course": "COEN 174"}], "anything")


def test_retrieved_snippets_only_from_caller(monkeypatch, db_path, alice, reply):
    """Even when both users have memory, A's plan never injects B's snippets."""
    bob = users_db.create_user("bob", "bob@example.com", "another solid password")
    memory_agent.write(bob, "preference", "BOB_SECRET_PHRASE: only Bob should ever see this")
    memory_agent.write(alice, "preference", "Alice loves morning labs")

    captured: list[str] = []
    _patch_client(monkeypatch, captured, reply)

    orchestrator.plan_for_user(
        alice,
        [{"course": "COEN 174", "category": "Core", "units": 4}],
        "morning preferences please",
    )

    prompt = captured[0]
    assert "BOB_SECRET_PHRASE" not in prompt
