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

import re

import pytest

from agents import memory_agent, orchestrator, planning_agent
from auth import users_db

from _llm_planner_stubs import patch_llm_planner


@pytest.fixture()
def alice(db_path):
    return users_db.create_user("alice", "alice@example.com", db_path=db_path)


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


def _patch_client(monkeypatch, captured_prompts, reply, *, extra_codes=()):
    patch_llm_planner(monkeypatch, captured_prompts, reply, extra_codes=extra_codes)


_MEMORY_BLOCK_RE = re.compile(
    r"(=== BACKGROUND CONTEXT[\s\S]*?)\n(?==== )",
)


def _extract_memory_block(prompt: str) -> str:
    """Return only the injected memory block, not later prompt sections."""
    match = _MEMORY_BLOCK_RE.search(prompt)
    assert match, "expected BACKGROUND CONTEXT block in prompt"
    return match.group(1)


def test_inject_retrieved_snippets_into_prompt_prefix(monkeypatch, alice, reply):
    memory_agent.write(alice, "preference", "Alice prefers no classes before 9am, quality over difficulty")
    memory_agent.write(alice, "plan_outcome", "Last quarter Alice took COEN 146 with prof X, total_units=12")

    captured: list[str] = []
    single_course_reply = {
        "recommended": [
            {"course": "COEN 174", "category": "Core", "units": 4, "reason": "team SE"},
        ],
        "total_units": 4,
        "advice": "Take core first.",
    }
    _patch_client(
        monkeypatch, captured, single_course_reply, extra_codes=("COEN 174",)
    )

    out = orchestrator.plan_for_user(
        alice,
        [{"course": "COEN 174", "category": "Core", "units": 4}],
        "easy quarter, prefer mornings",
    )

    assert out["total_units"] == 4
    assert len(captured) == 1
    prompt = captured[0]
    assert "BACKGROUND CONTEXT" in prompt
    assert prompt.index("BACKGROUND CONTEXT") < prompt.index(
        "STUDENT'S REMAINING REQUIREMENTS"
    )
    assert "Alice prefers no classes" in prompt or "Last quarter Alice took" in prompt


def test_prompt_prefix_respects_char_budget(monkeypatch, alice, reply):
    """With many medium snippets, the assembled block stays under budget."""
    medium = "x" * 400  # several of these together exceed the 1500 char budget
    for i in range(10):
        memory_agent.write(alice, "preference", f"{i}: {medium}")

    captured: list[str] = []
    _patch_client(
        monkeypatch, captured, reply, extra_codes=("COEN 174",)
    )

    orchestrator.plan_for_user(
        alice,
        [{"course": "COEN 174", "category": "Core", "units": 4}],
        "anything",
    )

    prompt = captured[0]
    memory_block = _extract_memory_block(prompt)
    assert len(memory_block) <= planning_agent.MEMORY_INJECT_CHAR_BUDGET, (
        f"Memory block is {len(memory_block)} chars, "
        f"budget {planning_agent.MEMORY_INJECT_CHAR_BUDGET}"
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
    _patch_client(
        monkeypatch, captured, reply, extra_codes=("COEN 174",)
    )

    orchestrator.plan_for_user(
        alice,
        [{"course": "COEN 174", "category": "Core", "units": 4}],
        "first time planning",
    )

    prompt = captured[0]
    assert "BACKGROUND CONTEXT" not in prompt, (
        "Prompt must not include an empty memory header when retrieval is empty"
    )
    assert "STUDENT'S REMAINING REQUIREMENTS" in prompt
    assert not prompt.lstrip().startswith("=== BACKGROUND CONTEXT")


def test_plan_for_user_writes_back_summary(monkeypatch, alice, reply):
    captured: list[str] = []
    single_course_reply = {
        "recommended": [
            {"course": "COEN 174", "category": "Core", "units": 4, "reason": "team SE"},
        ],
        "total_units": 4,
        "advice": "Take core first.",
    }
    _patch_client(
        monkeypatch, captured, single_course_reply, extra_codes=("COEN 174",)
    )

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
    assert "COEN 174" in new_row["content"]
    assert "total_units=4" in new_row["content"]


def test_plan_for_user_requires_user_id(monkeypatch, reply):
    captured: list[str] = []
    _patch_client(monkeypatch, captured, reply)
    with pytest.raises(ValueError):
        orchestrator.plan_for_user(None, [{"course": "COEN 174"}], "anything")


def test_preference_leading_trailing_whitespace_does_not_change_retrieve_query(
    monkeypatch, alice, reply
):
    """Embedding retrieval uses stripped preference; padded vs unpadded string must match."""
    captured: list[str] = []
    real_retrieve = memory_agent.retrieve

    def spy_retrieve(user_id, query, k=4, **kwargs):
        captured.append(query)
        return real_retrieve(user_id, query, k=k, **kwargs)

    monkeypatch.setattr(memory_agent, "retrieve", spy_retrieve)
    _patch_client(monkeypatch, [], reply)
    md = [{"course": "COEN 174", "category": "Core", "units": 4}]

    orchestrator.plan_for_user(alice, md, "  light load  ")
    orchestrator.plan_for_user(alice, md, "light load")

    assert len(captured) == 2
    assert captured[0] == captured[1]


def test_retrieved_snippets_only_from_caller(monkeypatch, db_path, alice, reply):
    """Even when both users have memory, A's plan never injects B's snippets."""
    bob = users_db.create_user("bob", "bob@example.com", db_path=db_path)
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
