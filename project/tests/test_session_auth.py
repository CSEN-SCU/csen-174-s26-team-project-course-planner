"""Session token auth for per-user API routes."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from auth.session_token import mint_session_token, verify_session_token


@pytest.fixture()
def client(db_path, monkeypatch):
    monkeypatch.setenv("REQUIRE_PLANNER_SESSION", "1")
    from main import app

    return TestClient(app)


def test_memory_requires_session_token(client):
    res = client.get("/api/memory/42")
    assert res.status_code == 401


def test_memory_rejects_mismatched_session(client):
    token = mint_session_token("99")
    res = client.get(
        "/api/memory/42",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 403


def test_session_token_round_trip():
    token = mint_session_token("123456789")
    assert verify_session_token(token) == "123456789"
