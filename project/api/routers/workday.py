"""
Workday sync router.

POST /api/workday/sync                  → {job_id}
GET  /api/workday/status/{job_id}       → {status, label, missing_details?, error?}
GET  /api/workday/configured            → {configured: bool, url: str}

Security notes:
  * Both POST /sync and GET /status require a ``user_id`` resolving to a real
    user in the SQLite ``users`` table. Anonymous callers get a 401 — this
    fixes the previously unauthenticated SSRF/abuse vector.
  * The user-supplied ``workday_url`` must match the SCU Workday allowlist
    regex; non-matching values are silently dropped in favor of the
    ``SCU_WORKDAY_URL`` env default, so the scraper never ``goto()``s an
    attacker-controlled host (no SSRF, no ``javascript:`` / ``file://``).
  * GET /status is scoped to the originating ``user_id``; a different user
    cannot read another job's state (closes IDOR).
  * Background scrape errors are passed through a curated label map before
    being shown to the UI; raw exception strings (which can leak stack-
    derived paths / module names) are only written to the server log via
    ``logging.exception``.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from agents.memory_agent import write as memory_write
from auth.users_db import get_user_by_id
from middleware.rate_limit import limit

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Workday URL allowlist ─────────────────────────────────────────────────────
#
# Only HTTPS URLs on SCU's Workday tenant are accepted from clients. We allow
# the bare apex (`myworkday.com`) plus the two production hostname variants
# SCU has historically served:
#   - https://www.myworkday.com/scu/...
#   - https://wd5.myworkday.com/scu/...
# Everything else (different tenants, other hosts, non-HTTPS, javascript:,
# file://, http://, etc.) is rejected; the server falls back to the
# SCU_WORKDAY_URL env default.

_WORKDAY_URL_ALLOWLIST = re.compile(r"^https://(www\.|wd5\.)?myworkday\.com/scu/.+")


def _validated_workday_url(candidate: str) -> str | None:
    """Return ``candidate`` if it matches the allowlist, else ``None``."""
    if not isinstance(candidate, str):
        return None
    trimmed = candidate.strip()
    if not trimmed:
        return None
    if _WORKDAY_URL_ALLOWLIST.match(trimmed):
        return trimmed
    return None


def _default_workday_url() -> str | None:
    """Return the configured default Workday URL, or ``None`` if unset."""
    env = (os.environ.get("SCU_WORKDAY_URL") or "").strip()
    return env or None


# ── Error scrubbing ───────────────────────────────────────────────────────────
#
# Raw exception messages can leak filesystem paths, module locations, and
# other stack-derived info to the browser. ``_scrub_error`` maps any exception
# to one of a fixed set of user-facing strings; the full traceback is still
# logged server-side for debugging.

_GENERIC_ERROR = "Sync failed. Try uploading manually with the 📎 button."


def _scrub_error(exc: BaseException) -> str:
    """Map ``exc`` to a curated, info-disclosure-safe message for the UI."""
    name = type(exc).__name__

    # Playwright-specific timeouts come through as PWTimeout / NavTimeout
    # but ``except`` should not import playwright at top level (it may be
    # missing in test envs), so match by class name.
    if name in {"PWTimeout", "PlaywrightTimeoutError", "NavTimeout", "TimeoutError"}:
        # The synchronous scraper raises a TimeoutError specifically for
        # SSO/login wait expiry; we phrase it as a login timeout so users
        # know to retry sooner.
        if isinstance(exc, TimeoutError):
            return "Login timed out. Please retry."
        return "Workday took too long to respond."

    if isinstance(exc, ModuleNotFoundError) or name in {"ImportError", "ModuleNotFoundError"}:
        return "Workday sync is not enabled on this server."

    return _GENERIC_ERROR


# ── In-memory job store ───────────────────────────────────────────────────────

_jobs: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()


def _set_job(job_id: str, **kwargs: Any) -> None:
    with _lock:
        _jobs.setdefault(job_id, {}).update(kwargs)


def _get_job(job_id: str) -> dict[str, Any]:
    with _lock:
        return dict(_jobs.get(job_id, {}))


# ── Status label map for the UI ───────────────────────────────────────────────

_STATUS_LABELS: dict[str, str] = {
    "pending":     "Starting browser…",
    "navigating":  "Opening Workday…",
    "browser_open": "Browser open — please complete your SCU login (SSO / MFA)",
    "logged_in":   "Login detected — finding your Academic Progress report…",
    "searching":   "Searching for View My Academic Progress…",
    "report_open": "Report found — exporting to Excel…",
    "downloading": "Downloading your Academic Progress file…",
    "parsing":     "Parsing your requirements…",
    "done":        "Done — transcript loaded!",
    "error":       "Sync failed.",
}


# ── Auth helper ───────────────────────────────────────────────────────────────


def _require_user(user_id: str | None) -> str:
    """Resolve ``user_id`` against the users table; raise 401 if missing/invalid.

    Returns the canonical string user_id on success so callers can compare
    requesters consistently.
    """
    uid_raw = (user_id or "").strip()
    if not uid_raw:
        raise HTTPException(status_code=401, detail="Authentication required.")
    user = get_user_by_id(uid_raw)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return str(user["id"])


# ── Background worker ─────────────────────────────────────────────────────────

def _run_scrape(job_id: str, user_id: str, workday_url: str | None) -> None:
    def cb(status: str) -> None:
        # Diagnostic statuses use the form "<code>::<detail>" — keep the
        # base code as job.status so the frontend's done/error detection
        # still works, but expose the detail in the label.
        if "::" in status:
            base, _, detail = status.partition("::")
            label = f"{_STATUS_LABELS.get(base, base)} — at {detail}"
            _set_job(job_id, status=base, label=label)
        else:
            _set_job(job_id, status=status, label=_STATUS_LABELS.get(status, status))

    try:
        from utils.workday_scraper import scrape_workday_sync
        result = scrape_workday_sync(workday_url=workday_url, progress_cb=cb)

        missing_details = result.get("missing_details") or []
        parsed_rows = result.get("parsed_rows") or []

        # Persist to memory just like the upload endpoint does
        if user_id:
            try:
                memory_write(user_id, "academic_progress", json.dumps(missing_details))
            except Exception:
                pass
            try:
                memory_write(user_id, "parsed_rows", json.dumps(parsed_rows))
            except Exception:
                pass

        _set_job(
            job_id,
            status="done",
            label=_STATUS_LABELS["done"],
            missing_details=missing_details,
            parsed_rows=parsed_rows,
        )
    except Exception as exc:  # noqa: BLE001
        # Log full traceback server-side; surface only a curated label to
        # the client so we don't leak filesystem paths / module names.
        logger.exception("Workday scrape failed for job_id=%s", job_id)
        _set_job(
            job_id,
            status="error",
            label=_STATUS_LABELS["error"],
            error=_scrub_error(exc),
        )


# ── Endpoints ─────────────────────────────────────────────────────────────────

class SyncRequest(BaseModel):
    user_id: str = ""
    workday_url: str = ""


@router.post("/sync", dependencies=[Depends(limit("workday_sync"))])
def start_sync(body: SyncRequest) -> dict[str, str]:
    """Launch a background Playwright scrape and return a job_id to poll."""
    user_id = _require_user(body.user_id)

    # Validate the client-supplied URL against the allowlist; if it fails
    # or is empty, fall back to the configured SCU default. This is the
    # SSRF defense — the scraper will never goto() an unvetted URL.
    url = _validated_workday_url(body.workday_url) or _default_workday_url()

    job_id = str(uuid.uuid4())
    _set_job(
        job_id,
        status="pending",
        label=_STATUS_LABELS["pending"],
        user_id=user_id,
    )

    t = threading.Thread(
        target=_run_scrape,
        args=(job_id, user_id, url),
        daemon=True,
    )
    t.start()
    return {"job_id": job_id}


@router.get("/status/{job_id}")
def get_status(job_id: str, user_id: str = Query("", description="Requester user_id")) -> dict[str, Any]:
    requester = _require_user(user_id)
    job = _get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    if job.get("user_id") != requester:
        # Don't disclose whether the job exists for another user — return
        # 404 (not 403) so an attacker can't enumerate other users' jobs.
        raise HTTPException(status_code=404, detail="Job not found.")
    # Strip the internal originator id from the response.
    return {k: v for k, v in job.items() if k != "user_id"}


@router.get("/configured")
def is_configured() -> dict[str, Any]:
    url = os.environ.get("SCU_WORKDAY_URL", "").strip()
    return {
        "configured": bool(url),
        "url": url or "",
        "default_url": "https://www.myworkday.com/scu/d/task/2998$44123.htmld",
    }
