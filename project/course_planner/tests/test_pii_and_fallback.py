"""Spec §8 / §11: PII redaction and embeddings fallback safety nets.

These tests pin down two behaviors that protect the prototype when
things go off the happy path:

1. Memory snippets retrieved from the DB are scrubbed for emails / SSNs /
   phone numbers *before* they are injected into a Gemini prompt.
2. ``memory_agent.embed`` falls back to a deterministic hash-based vector
   when ``GEMINI_API_KEY`` is missing, so writes never block users.
"""

from __future__ import annotations

import pytest

from agents import memory_agent, orchestrator, planning_agent
from auth import users_db


def _stub_planning(monkeypatch, captured: list[str]):
    """Stub run_planning_agent's HTTP path for prompt assertions."""
    import json
    from types import SimpleNamespace

    class _Models:
        def generate_content(self, model, contents, config):
            captured.append(contents)
            return SimpleNamespace(text=json.dumps({"recommended": [], "total_units": 0, "advice": "x"}))

    class _Client:
        models = _Models()

    monkeypatch.setattr(planning_agent, "get_genai_client", lambda **_kw: _Client())


@pytest.fixture()
def alice(db_path):
    return users_db.create_user("alice", "alice@example.com", "correct horse battery", db_path=db_path)


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
