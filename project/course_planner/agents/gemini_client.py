"""Lazy shared Gemini client keyed from the same env vars as schedule generation."""

from __future__ import annotations

import os

from google import genai

_client: genai.Client | None = None


def get_genai_client(*, purpose: str) -> genai.Client:
    """Return a process-wide client; requires GEMINI_API_KEY or GOOGLE_API_KEY."""
    global _client
    if _client is None:
        key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not key:
            raise ValueError(
                f"GEMINI_API_KEY (or GOOGLE_API_KEY) is not set; cannot run {purpose}."
            )
        _client = genai.Client(api_key=key)
    return _client


def reset_client_for_tests() -> None:
    global _client
    _client = None
