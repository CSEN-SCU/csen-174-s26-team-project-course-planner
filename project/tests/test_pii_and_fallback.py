"""Spec §8 / §11: PII redaction and embeddings fallback safety nets.

These tests pin down two behaviors that protect the prototype when
things go off the happy path:

1. Memory snippets retrieved from the store are scrubbed for emails / SSNs /
   phone numbers *before* they are injected into a Gemini prompt.
   This covers both the orchestrator path (``orchestrator.plan_for_user``)
   and the direct API-router path (``POST /api/plan``).
2. ``memory_agent.embed`` falls back to a deterministic hash-based vector
   when ``GEMINI_API_KEY`` is missing, so writes never block users.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from agents import memory_agent, orchestrator, planning_agent
from auth import users_db

from _llm_planner_stubs import patch_llm_planner

_API_DIR = Path(__file__).resolve().parents[1] / "api"


def _load_api_main(monkeypatch, tmp_path):
    if str(_API_DIR) not in sys.path:
        sys.path.insert(0, str(_API_DIR))
    monkeypatch.setenv("COURSE_PLANNER_DB", str(tmp_path / "pii_api.db"))
    monkeypatch.setenv("COURSE_PLANNER_MEMORY_DIR", str(tmp_path / "memory"))
    sys.modules.pop("main", None)
    return importlib.import_module("main")


def _stub_planning(monkeypatch, captured: list[str]):
    """Stub orchestrator's LLM planner path for prompt assertions."""
    patch_llm_planner(
        monkeypatch,
        captured,
        {"recommended": [], "total_units": 0, "advice": "x"},
        extra_codes=("COEN 174",),
    )


@pytest.fixture()
def alice(db_path):
    return users_db.create_user("alice", "alice@example.com", db_path=db_path)


def test_redact_pii_strips_emails_and_id_numbers():
    raw = "PREF: contact me at jane.doe@scu.edu, SID 123-45-6789, phone +1 (408) 555-1234"

    cleaned = orchestrator._redact_pii(raw)

    assert "jane.doe@scu.edu" not in cleaned
    assert "123-45-6789" not in cleaned
    assert "[redacted-email]" in cleaned
    assert "[redacted-id]" in cleaned
    assert "[redacted-phone]" in cleaned


def test_redact_pii_keeps_course_codes_intact():
    raw = "PREF: easy quarter\nGAP: COEN 146, COEN 174, ELEN 153\nPLAN: total_units=12"

    cleaned = orchestrator._redact_pii(raw)

    assert "COEN 146" in cleaned
    assert "COEN 174" in cleaned
    assert "ELEN 153" in cleaned
    assert "total_units=12" in cleaned


def test_orchestrator_redacts_memory_before_injection(monkeypatch, alice):
    memory_agent.write(
        alice,
        "preference",
        "Remind me to email tutor.kim@scu.edu and call 408-555-1234 about COEN 174",
    )
    captured: list[str] = []
    _stub_planning(monkeypatch, captured)

    orchestrator.plan_for_user(
        alice,
        [{"course": "COEN 174", "category": "Core", "units": 4}],
        "easy quarter",
    )

    prompt = captured[0]
    assert "tutor.kim@scu.edu" not in prompt
    assert "408-555-1234" not in prompt
    assert "[redacted-email]" in prompt
    assert "COEN 174" in prompt  # course codes survive


def test_embed_falls_back_when_no_api_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    vec_a = memory_agent.embed("alice prefers morning labs")
    vec_b = memory_agent.embed("alice prefers morning labs")
    vec_c = memory_agent.embed("totally different preference signal")

    assert len(vec_a) == 768
    assert vec_a == vec_b, "fallback embedder must be deterministic for stable retrieval"
    assert vec_a != vec_c, "different texts must produce different fallback vectors"
    assert all(-1.0 <= x <= 1.0 for x in vec_a)


def test_embed_handles_empty_string():
    """Empty input must not crash; returns a zero vector of the right dim."""
    vec = memory_agent.embed("")
    assert len(vec) == 768
    assert all(x == 0.0 for x in vec)


# ── API-router path: memory snippets must be redacted before reaching Gemini ──


def test_api_plan_router_redacts_pii_in_memory_before_prompt(monkeypatch, tmp_path):
    """POST /api/plan must scrub PII from stored memory before injecting into the
    Gemini prompt, even when bypassing the orchestrator layer.

    Regression guard: plan.py previously passed raw memory snippets to the
    planner without calling _redact_pii. The default planner is now the LLM
    course-selection engine, so this stubs its Gemini call and asserts memory
    snippets are redacted before they reach the prompt.
    """
    from fastapi.testclient import TestClient

    from agents import planning_agent_llm

    captured_prompts: list[str] = []
    prose_reply = json.dumps({"assistant_reply": "ok", "advice": "ok"})

    class _Models:
        def generate_content(self, model, contents, config):  # noqa: D401
            captured_prompts.append(contents)
            return SimpleNamespace(text=prose_reply)

    class _Client:
        models = _Models()

    # 1. Set up an isolated DB + memory store and create a test user.
    monkeypatch.setenv("COURSE_PLANNER_DB", str(tmp_path / "pii_api.db"))
    mem_dir = tmp_path / "memory"
    mem_dir.mkdir()
    monkeypatch.setenv("COURSE_PLANNER_MEMORY_DIR", str(mem_dir))
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    from db.migrate import migrate

    migrate(str(tmp_path / "pii_api.db"))
    uid = users_db.create_user("pii_user", "pii@example.com")

    # 2. Write a memory snippet containing PII into the user's store.
    memory_agent.write(
        uid,
        "preference",
        "Contact advisor.lee@scu.edu or call +1 (408) 555-9876 about COEN 174",
    )

    # 3. Load the app and wire the stub Gemini client for the LLM planner call.
    main = _load_api_main(monkeypatch, tmp_path)
    monkeypatch.setattr("routers.plan.get_genai_client", lambda **_kw: _Client())
    monkeypatch.setattr(planning_agent, "get_genai_client", lambda **_kw: _Client())
    monkeypatch.setattr(planning_agent_llm, "get_genai_client", lambda **_kw: _Client())

    with TestClient(main.app) as client:
        resp = client.post(
            "/api/plan",
            json={
                "missing_details": [{"course": "COEN 174", "category": "Core", "units": 4}],
                "user_preference": "easy quarter",
                "user_id": str(uid),
            },
        )

    assert resp.status_code == 200

    # 4. The combined prompt must NOT contain raw PII.
    full_prompt = " ".join(str(p) for p in captured_prompts)
    assert captured_prompts, "LLM planner call was not stubbed/captured"
    assert "advisor.lee@scu.edu" not in full_prompt, "email PII leaked into LLM prompt"
    assert "555-9876" not in full_prompt, "phone PII leaked into LLM prompt"
    # Redaction placeholders must appear instead.
    assert "[redacted-email]" in full_prompt
    assert "[redacted-phone]" in full_prompt
    # Course codes must survive redaction (in memory block and/or finalized plan).
    assert "COEN 174" in full_prompt
