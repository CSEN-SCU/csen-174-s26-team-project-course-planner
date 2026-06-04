from __future__ import annotations

import json

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from agents.memory_agent import write as memory_write
from deps.user_auth import require_matching_user
from utils.academic_progress_helpers import enrich_missing_details
from utils.academic_progress_xlsx import parse_academic_progress_xlsx, sanitize_parsed_rows
from utils.major_requirements import detect_major_detailed

router = APIRouter()
_MAX_TRANSCRIPT_BYTES = 5 * 1024 * 1024  # 5 MiB


@router.post("/transcript")
async def upload_transcript(
    request: Request,
    file: UploadFile = File(...),
    user_id: str = Form(""),
) -> dict:
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(
            status_code=400,
            detail="Expected an Academic Progress export (.xlsx).",
        )
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty file.")
    if len(raw) > _MAX_TRANSCRIPT_BYTES:
        raise HTTPException(
            status_code=413,
            detail="File too large. Max upload size is 5 MB.",
        )
    try:
        data = parse_academic_progress_xlsx(raw)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    parsed_rows = sanitize_parsed_rows(data.get("detail_rows") or [])
    missing_details = enrich_missing_details(data.get("not_satisfied") or [], parsed_rows)

    uid = user_id.strip()
    if uid:
        require_matching_user(request, uid)
        try:
            memory_write(uid, "academic_progress", json.dumps(missing_details))
        except Exception:  # noqa: BLE001
            pass
        try:
            # Persist completed-course history so the 4-year plan can render
            # past quarters after the student logs back in
            memory_write(uid, "parsed_rows", json.dumps(parsed_rows))
        except Exception:  # noqa: BLE001
            pass

    major_detection = detect_major_detailed(missing_details, parsed_rows)

    return {
        "missing_details": missing_details,
        "parsed_rows": parsed_rows,
        "major_detection": major_detection,
    }
