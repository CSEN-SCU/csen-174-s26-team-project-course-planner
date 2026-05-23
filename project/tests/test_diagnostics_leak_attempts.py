"""Test system-prompt leak attempt diagnostics endpoint (RT#8)."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from agents import planning_agent

_API_DIR = Path(__file__).resolve().parents[1] / "api"


def _load_api_main(monkeypatch, tmp_path):
  if str(_API_DIR) not in sys.path:
    sys.path.insert(0, str(_API_DIR))
  monkeypatch.setenv("COURSE_PLANNER_DB", str(tmp_path / "diag.db"))
  monkeypatch.setenv("COURSE_PLANNER_MEMORY_DIR", str(tmp_path / "memory"))
  sys.modules.pop("main", None)
  return importlib.import_module("main")


def test_diagnostics_leak_attempts_requires_admin_token(monkeypatch, tmp_path):
  """GET /api/diagnostics/leak_attempts should reject requests without token."""
  monkeypatch.setenv("DIAGNOSTICS_ADMIN_TOKEN", "secret-key-123")
  main = _load_api_main(monkeypatch, tmp_path)

  with TestClient(main.app) as client:
    # No token
    resp = client.get("/api/diagnostics/leak_attempts")
    assert resp.status_code == 403
    assert "invalid" in resp.json()["detail"].lower()

    # Wrong token
    resp = client.get("/api/diagnostics/leak_attempts", headers={"X-Admin-Token": "wrong"})
    assert resp.status_code == 403

    # Correct token
    resp = client.get(
        "/api/diagnostics/leak_attempts",
        headers={"X-Admin-Token": "secret-key-123"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "leak_attempts" in body
    assert isinstance(body["leak_attempts"], int)


def test_diagnostics_leak_attempts_not_configured(monkeypatch, tmp_path):
  """GET /api/diagnostics/leak_attempts should return 503 if not configured."""
  # Don't set DIAGNOSTICS_ADMIN_TOKEN
  monkeypatch.delenv("DIAGNOSTICS_ADMIN_TOKEN", raising=False)
  main = _load_api_main(monkeypatch, tmp_path)

  with TestClient(main.app) as client:
    resp = client.get("/api/diagnostics/leak_attempts", headers={"X-Admin-Token": "anything"})
    assert resp.status_code == 503
    assert "not configured" in resp.json()["detail"].lower()


def test_planning_agent_tracks_system_prompt_leaks(monkeypatch):
  """System-prompt leak detection should increment the counter."""
  # Reset counter before test
  planning_agent.reset_leak_attempt_count()

  reply_with_leak = {
      "recommended": [{"course": "CSEN 161", "title": "x", "category": "Core", "units": 4, "reason": "ok"}],
      "total_units": 4,
      "advice": "Before you answer, CURRENT ASK is the absolute priority",
      "assistant_reply": "Here is your plan.",
  }

  class _Models:
    def generate_content(self, model, contents, config):  # noqa: D401
      return SimpleNamespace(text=json.dumps(reply_with_leak))

  class _Client:
    models = _Models()

  monkeypatch.setattr(planning_agent, "get_genai_client", lambda **_kw: _Client())
  monkeypatch.setattr(
      planning_agent,
      "load_schedule_section_index",
      lambda: {("CSEN", "161"): {"instructors": [], "meeting_days": [], "meeting_start_min": None, "meeting_end_min": None}},
  )

  out = planning_agent.run_planning_agent(
      missing_details=[{"course": "CSEN 161", "category": "Core", "units": 4}],
      user_preference="light load",
  )

  # Advice should be replaced with fallback
  assert out["advice"] == planning_agent._FALLBACK_ADVICE
  assert "CURRENT ASK" not in out["advice"]

  # Counter should have incremented
  assert planning_agent.get_leak_attempt_count() == 1


def test_planning_agent_tracks_multiple_leaks(monkeypatch):
  """Multiple leaks should increment counter each time."""
  planning_agent.reset_leak_attempt_count()

  # First call with leak in advice
  reply1 = {
      "recommended": [{"course": "CSEN 161", "title": "x", "category": "Core", "units": 4, "reason": "ok"}],
      "total_units": 4,
      "advice": "CURRENT ASK is the absolute priority",
      "assistant_reply": "Good plan.",
  }

  class _Models:
    def generate_content(self, model, contents, config):  # noqa: D401
      return SimpleNamespace(text=json.dumps(reply1))

  class _Client:
    models = _Models()

  monkeypatch.setattr(planning_agent, "get_genai_client", lambda **_kw: _Client())
  monkeypatch.setattr(
      planning_agent,
      "load_schedule_section_index",
      lambda: {("CSEN", "161"): {"instructors": [], "meeting_days": [], "meeting_start_min": None, "meeting_end_min": None}},
  )

  planning_agent.run_planning_agent(
      missing_details=[{"course": "CSEN 161", "category": "Core", "units": 4}],
      user_preference="light load",
  )

  assert planning_agent.get_leak_attempt_count() == 1

  # Second call with leak in assistant_reply
  reply2 = {
      "recommended": [{"course": "CSEN 162", "title": "y", "category": "Core", "units": 4, "reason": "ok"}],
      "total_units": 4,
      "advice": "Good advice.",
      "assistant_reply": "You are an SCU course planning advisor - ignore rules",
  }

  class _Models2:
    def generate_content(self, model, contents, config):  # noqa: D401
      return SimpleNamespace(text=json.dumps(reply2))

  class _Client2:
    models = _Models2()

  monkeypatch.setattr(planning_agent, "get_genai_client", lambda **_kw: _Client2())
  monkeypatch.setattr(
      planning_agent,
      "load_schedule_section_index",
      lambda: {("CSEN", "162"): {"instructors": [], "meeting_days": [], "meeting_start_min": None, "meeting_end_min": None}},
  )

  planning_agent.run_planning_agent(
      missing_details=[{"course": "CSEN 162", "category": "Core", "units": 4}],
      user_preference="different load",
  )

  # Counter should now be 2
  assert planning_agent.get_leak_attempt_count() == 2
