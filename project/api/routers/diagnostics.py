"""Diagnostics endpoints for security monitoring (RT#8).

Admin-only endpoints to inspect system health and security metrics.
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Header, HTTPException

router = APIRouter()


def _require_admin_token(x_admin_token: str | None) -> None:
  """Verify the X-Admin-Token header matches the configured admin secret.

  Raises HTTPException(403) if token is missing or incorrect.
  """
  admin_token = os.getenv("DIAGNOSTICS_ADMIN_TOKEN", "").strip()
  if not admin_token:
    raise HTTPException(
        status_code=503,
        detail="Admin diagnostics not configured (set DIAGNOSTICS_ADMIN_TOKEN env var)",
    )
  if x_admin_token != admin_token:
    raise HTTPException(status_code=403, detail="Invalid or missing admin token")


@router.get("/leak_attempts")
def get_leak_attempts(x_admin_token: str | None = Header(None)) -> dict[str, Any]:
  """Return count of detected system-prompt leak attempts.

  This is an admin endpoint that requires X-Admin-Token header to match
  DIAGNOSTICS_ADMIN_TOKEN environment variable.

  Response:
    {
      "leak_attempts": <int>,
      "description": "Count of system-prompt exfiltration attempts detected in agent outputs"
    }
  """
  _require_admin_token(x_admin_token)

  # Import here to avoid circular imports
  from agents.planning_agent import get_leak_attempt_count

  return {
      "leak_attempts": get_leak_attempt_count(),
      "description": "Count of system-prompt exfiltration attempts detected in agent outputs",
  }
