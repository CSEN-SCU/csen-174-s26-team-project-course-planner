"""
Workday headed-browser pull (local dev).

POST /api/workday/sync                  → {job_id}
GET  /api/workday/status/{job_id}       → {status, label, missing_details?, error?}
GET  /api/workday/available             → {available: bool}

The student completes SSO + Duo in a visible Chromium window on the machine
where the API runs. No SCU passwords are stored — only a gitignored browser
profile under ``course_planner/.workday_profile/``.

Disabled on hosts without Playwright or when ``SCU_WORKDAY_PULL_ENABLED=0``.
"""
from __future__ import annotations

import logging
import os
import threading
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from auth.users_db import get_user_by_id
from middleware.rate_limit import limit

logger = logging.getLogger(__name__)
router = APIRouter()

_STATUS_LABELS: dict[str, str] = {
    "pending": "Starting browser…",
    "browser_open": "Browser open — complete SCU login and Duo in that window",
    "logged_in": "Login detected — opening Academic Progress…",
    "navigating": "Opening View My Academic Progress…",
    "report_open": "Report ready — exporting to Excel…",
    "downloading": "Opening report and looking for Export to Excel…",
    "exporting": "Click the Excel icon on the report (or wait — retrying every few seconds)…",
    "parsing": "Parsing your requirements…",
    "done": "Done — transcript loaded!",
    "error": "Sync failed.",
}

_GENERIC_ERROR = "Sync failed. Try uploading manually with the paperclip button."


def _playwright_importable() -> bool:
    try:
        import playwright  # noqa: F401
    except ImportError:
        return False
    return True


def workday_pull_enabled() -> bool:
    """Whether the API may start a headed Workday pull on this host."""
    flag = (os.environ.get("SCU_WORKDAY_PULL_ENABLED") or "").strip().lower()
    if flag in ("0", "false", "no", "off"):
        return False
    if flag in ("1", "true", "yes", "on"):
        return _playwright_importable()
    # Default: on when Playwright is installed (typical local dev).
    return _playwright_importable()


def _scrub_error(exc: BaseException) -> str:
    name = type(exc).__name__
    if name in {"PWTimeout", "PlaywrightTimeoutError", "TimeoutError"}:
        if isinstance(exc, TimeoutError):
            return "Login timed out. Complete SSO and Duo in the browser window, then try again."
        return "Workday took too long to respond."
    if isinstance(exc, ModuleNotFoundError) or name in {"ImportError", "ModuleNotFoundError"}:
        return "Workday sync is not enabled on this server."
    msg = str(exc).strip()
    if "ZERO rows" in msg or "layout may have changed" in msg:
        return (
            "The export did not contain course requirements. Wait for the full report "
            "to load in Workday, then try again — or upload the .xlsx with the paperclip."
        )
    if "Could not reach" in msg or "Find Course Sections" in msg:
        return "Could not open Academic Progress in Workday. Try again or upload manually."
    return _GENERIC_ERROR


_jobs: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()


def _set_job(job_id: str, **kwargs: Any) -> None:
    with _lock:
        _jobs.setdefault(job_id, {}).update(kwargs)


def _get_job(job_id: str) -> dict[str, Any]:
    with _lock:
        return dict(_jobs.get(job_id, {}))


def _require_user(user_id: str | None) -> str:
    uid_raw = (user_id or "").strip()
    if not uid_raw:
        raise HTTPException(status_code=401, detail="Authentication required.")
    user = get_user_by_id(uid_raw)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return str(user["id"])


def _run_pull(job_id: str, user_id: str) -> None:
    def cb(status: str) -> None:
        _set_job(job_id, status=status, label=_STATUS_LABELS.get(status, status))

    try:
        from scripts.workday_pull_progress import ProgressValidationError, pull_academic_progress

        result = pull_academic_progress(user_id, progress_cb=cb)
        _set_job(
            job_id,
            status="done",
            label=_STATUS_LABELS["done"],
            missing_details=result.get("missing_details") or [],
            parsed_rows=result.get("parsed_rows") or [],
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Workday pull failed for job_id=%s", job_id)
        _set_job(
            job_id,
            status="error",
            label=_STATUS_LABELS["error"],
            error=_scrub_error(exc),
        )


class SyncRequest(BaseModel):
    user_id: str = ""


@router.get("/available")
def workday_available() -> dict[str, bool]:
    return {"available": workday_pull_enabled()}


@router.post("/sync", dependencies=[Depends(limit("workday_sync"))])
def start_sync(body: SyncRequest) -> dict[str, str]:
    if not workday_pull_enabled():
        raise HTTPException(
            status_code=503,
            detail="Workday sync is not available on this server. Upload your .xlsx export instead.",
        )
    user_id = _require_user(body.user_id)
    job_id = str(uuid.uuid4())
    _set_job(
        job_id,
        status="pending",
        label=_STATUS_LABELS["pending"],
        user_id=user_id,
    )
    threading.Thread(target=_run_pull, args=(job_id, user_id), daemon=True).start()
    return {"job_id": job_id}


@router.get("/status/{job_id}")
def get_status(
    job_id: str,
    user_id: str = Query("", description="Requester user_id"),
) -> dict[str, Any]:
    requester = _require_user(user_id)
    job = _get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    if job.get("user_id") != requester:
        raise HTTPException(status_code=404, detail="Job not found.")
    return {k: v for k, v in job.items() if k != "user_id"}
