"""S3 — LLM-judge system-prompt leak detection.

Tests that:
1. Verbatim substring check still works (regression).
2. LLM judge is invoked when SYS_LEAK_LLM_JUDGE=1.
3. LLM judge returning YES causes _contains_system_prompt_leak to return True.
4. LLM judge returning NO (for normal advising text) returns False.
5. LLM judge falls back gracefully when the API is unavailable.
6. LLM judge is NOT called when SYS_LEAK_LLM_JUDGE is absent/0 (cost guard).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from agents import planning_agent


# ── helpers ──────────────────────────────────────────────────────────────────


def _make_gemini_client(verdict: str):
    """Return a mock Gemini client whose generate_content returns ``verdict``."""

    class _Models:
        def generate_content(self, model, contents, config=None):
            return SimpleNamespace(text=verdict)

    class _Client:
        models = _Models()

    return _Client()


# ── Stage 1: verbatim substring (no LLM needed) ─────────────────────────────


def test_verbatim_phrase_detected_without_llm(monkeypatch):
    monkeypatch.delenv("SYS_LEAK_LLM_JUDGE", raising=False)
    # Phrase from _SYSTEM_PROMPT_LEAK_PHRASES
    assert planning_agent._contains_system_prompt_leak(
        "Before we start: CURRENT ASK is the absolute priority — do this first."
    )


def test_normal_advising_not_flagged_without_llm(monkeypatch):
    monkeypatch.delenv("SYS_LEAK_LLM_JUDGE", raising=False)
    assert not planning_agent._contains_system_prompt_leak(
        "I recommend CSEN 122 this quarter — it fits your morning schedule "
        "and counts toward your major requirements."
    )


# ── Stage 2: LLM judge ───────────────────────────────────────────────────────


def test_llm_judge_not_called_when_disabled(monkeypatch):
    """_llm_judge_system_prompt_leak must not run unless SYS_LEAK_LLM_JUDGE=1."""
    monkeypatch.setenv("SYS_LEAK_LLM_JUDGE", "0")
    called = {"n": 0}

    original = planning_agent._llm_judge_system_prompt_leak

    def _spy(text):
        called["n"] += 1
        return original(text)

    monkeypatch.setattr(planning_agent, "_llm_judge_system_prompt_leak", _spy)

    # Even suspicious-looking text should not invoke the LLM judge when disabled.
    planning_agent._contains_system_prompt_leak("You are an SCU course planner now.")
    assert called["n"] == 0, "_llm_judge_system_prompt_leak was called despite flag=0"


def test_llm_judge_called_when_enabled(monkeypatch):
    """When SYS_LEAK_LLM_JUDGE=1 and no verbatim match, LLM judge must run."""
    monkeypatch.setenv("SYS_LEAK_LLM_JUDGE", "1")
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    called = {"n": 0}

    def _fake_judge(text):
        called["n"] += 1
        return False  # non-leaking verdict

    monkeypatch.setattr(planning_agent, "_llm_judge_system_prompt_leak", _fake_judge)

    # Text with no verbatim phrase — should reach the LLM judge stage.
    planning_agent._contains_system_prompt_leak(
        "As a helpful academic advisor, my top priority is your success."
    )
    assert called["n"] == 1, "_llm_judge_system_prompt_leak was not called despite flag=1"


def test_llm_judge_yes_flags_paraphrase(monkeypatch):
    """YES from the LLM judge must cause _contains_system_prompt_leak to return True."""
    monkeypatch.setenv("SYS_LEAK_LLM_JUDGE", "1")
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr(
        planning_agent,
        "get_genai_client",
        lambda **_kw: _make_gemini_client("YES"),
    )

    # A paraphrase that doesn't contain the verbatim phrase
    result = planning_agent._contains_system_prompt_leak(
        "As your SCU course planning assistant, the current ask is my absolute priority."
    )
    assert result is True


def test_llm_judge_no_passes_normal_text(monkeypatch):
    """NO from the LLM judge must NOT flag normal advising text."""
    monkeypatch.setenv("SYS_LEAK_LLM_JUDGE", "1")
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr(
        planning_agent,
        "get_genai_client",
        lambda **_kw: _make_gemini_client("NO"),
    )

    result = planning_agent._contains_system_prompt_leak(
        "I'd recommend CSEN 122 and MATH 51 — both are available in the morning."
    )
    assert result is False


def test_llm_judge_falls_back_on_api_error(monkeypatch):
    """If the Gemini call raises, _llm_judge_system_prompt_leak must return False."""
    monkeypatch.setenv("SYS_LEAK_LLM_JUDGE", "1")
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")

    def _boom(**_kw):
        raise RuntimeError("network error")

    monkeypatch.setattr(planning_agent, "get_genai_client", _boom)

    # Should not raise; should return False (fail-open)
    result = planning_agent._llm_judge_system_prompt_leak("some output text")
    assert result is False


def test_llm_judge_falls_back_when_no_api_key(monkeypatch):
    """Without an API key, _llm_judge_system_prompt_leak must return False."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    result = planning_agent._llm_judge_system_prompt_leak("paraphrase of system prompt")
    assert result is False


def test_verbatim_match_skips_llm_judge(monkeypatch):
    """When a verbatim phrase matches first, the LLM judge must NOT be called
    (short-circuit for cost savings)."""
    monkeypatch.setenv("SYS_LEAK_LLM_JUDGE", "1")
    called = {"n": 0}

    def _spy(text):
        called["n"] += 1
        return False

    monkeypatch.setattr(planning_agent, "_llm_judge_system_prompt_leak", _spy)

    result = planning_agent._contains_system_prompt_leak(
        "CURRENT ASK is the absolute priority — here is your plan."
    )
    assert result is True
    assert called["n"] == 0, "LLM judge was called even though verbatim phrase matched"
