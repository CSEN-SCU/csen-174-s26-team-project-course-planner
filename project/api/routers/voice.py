from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile
from google.genai import types

from agents.gemini_client import get_genai_client

router = APIRouter()

_TRANSCRIBE_PROMPT = (
    "Transcribe the speech in this audio recording. "
    "Return only the exact spoken words with no additional commentary or punctuation beyond what was said."
)


@router.post("/transcribe")
async def transcribe_audio(file: UploadFile = File(...)) -> dict[str, str]:
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty audio file.")

    mime_type = (file.content_type or "audio/webm").split(";")[0].strip()
    allowed = {
        "audio/webm", "audio/ogg", "audio/mp4", "audio/mpeg",
        "audio/wav", "audio/flac", "audio/aac",
    }
    if mime_type not in allowed:
        mime_type = "audio/webm"

    try:
        client = get_genai_client(purpose="audio transcription")
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                types.Part.from_bytes(data=raw, mime_type=mime_type),
                _TRANSCRIBE_PROMPT,
            ],
        )
        transcript = (response.text or "").strip()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {"transcript": transcript}
