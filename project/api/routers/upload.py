from __future__ import annotations

import json

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from agents.memory_agent import write as memory_write
from utils.academic_progress_xlsx import parse_academic_progress_xlsx

router = APIRouter()


@router.post("/transcript")
async def upload_transcript(
    file: UploadFile = File(...),
    user_id: str = Form(""),
) -> dict:
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(
            status_code=400,
            detail="Expected an Excel file (.xlsx or .xlsm).",
        )
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty file.")
    try:
        data = parse_academic_progress_xlsx(raw)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    missing_details = data.get("not_satisfied") or []
    parsed_rows = data.get("detail_rows") or []

    uid = user_id.strip()
    if uid:
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

    return {
        "missing_details": missing_details,
        "parsed_rows": parsed_rows,
    }
