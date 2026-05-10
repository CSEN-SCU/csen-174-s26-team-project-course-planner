from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile

from utils.academic_progress_xlsx import parse_academic_progress_xlsx

router = APIRouter()


@router.post("/transcript")
async def upload_transcript(file: UploadFile = File(...)) -> dict:
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
    except Exception as exc:  # noqa: BLE001 — surface parse errors to client
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "missing_details": data.get("not_satisfied") or [],
        "parsed_rows": data.get("detail_rows") or [],
    }
