"""
Workday sync router.

POST /api/workday/sync      → {job_id}
GET  /api/workday/status/{job_id} → {status, label, missing_details?, error?}
GET  /api/workday/configured      → {configured: bool, url: str}
"""
from __future__ import annotations

import json
import os
import threading
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agents.memory_agent import write as memory_write

router = APIRouter()

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


# ── Background worker ─────────────────────────────────────────────────────────

def _run_scrape(job_id: str, user_id: str, workday_url: str | None) -> None:
    def cb(status: str) -> None:
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

        _set_job(
            job_id,
            status="done",
            label=_STATUS_LABELS["done"],
            missing_details=missing_details,
            parsed_rows=parsed_rows,
        )
    except Exception as exc:  # noqa: BLE001
        _set_job(
            job_id,
            status="error",
            label=_STATUS_LABELS["error"],
            error=str(exc),
        )


# ── Endpoints ─────────────────────────────────────────────────────────────────

class SyncRequest(BaseModel):
    user_id: str = ""
    workday_url: str = ""


@router.post("/sync")
def start_sync(body: SyncRequest) -> dict[str, str]:
    """Launch a background Playwright scrape and return a job_id to poll."""
    job_id = str(uuid.uuid4())
    _set_job(job_id, status="pending", label=_STATUS_LABELS["pending"])

    url = body.workday_url.strip() or os.environ.get("SCU_WORKDAY_URL") or None
    t = threading.Thread(
        target=_run_scrape,
        args=(job_id, body.user_id.strip(), url),
        daemon=True,
    )
    t.start()
    return {"job_id": job_id}


@router.get("/status/{job_id}")
def get_status(job_id: str) -> dict[str, Any]:
    job = _get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job


@router.get("/configured")
def is_configured() -> dict[str, Any]:
    url = os.environ.get("SCU_WORKDAY_URL", "").strip()
    return {
        "configured": bool(url),
        "url": url or "",
        "default_url": "https://wd5.myworkday.com/scu/d/home.htmld",
    }
