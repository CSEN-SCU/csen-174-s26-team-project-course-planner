from __future__ import annotations

import os
import sys

# Resolve course_planner package root (sibling of this api directory).
_API_DIR = os.path.dirname(os.path.abspath(__file__))
_COURSE_PLANNER = os.path.normpath(os.path.join(_API_DIR, "..", "course_planner"))
sys.path.insert(0, _COURSE_PLANNER)

from dotenv import load_dotenv

# Same env file as Streamlit (`course_planner/.env`) so GEMINI_API_KEY is picked up by agents.
_env_cp = os.path.join(_COURSE_PLANNER, ".env")
if os.path.isfile(_env_cp):
    load_dotenv(_env_cp)
_env_api = os.path.join(_API_DIR, ".env")
if os.path.isfile(_env_api):
    load_dotenv(_env_api, override=True)

from typing import Dict

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from middleware.rate_limit import RateLimitExceeded
from routers import auth, four_year_plan, memory, plan, upload, voice, workday

app = FastAPI(title="SCU Course Planner API")


@app.exception_handler(RateLimitExceeded)
async def _rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Return rate-limit denials as a flat JSON body the frontend can switch on.

    Without this handler FastAPI would nest the payload under ``detail`` (its
    default for ``HTTPException``). The spec calls for a top-level ``error``
    field so the UI can distinguish 429s from the existing 400/502 errors
    without parsing.
    """
    detail = exc.detail if isinstance(exc.detail, dict) else {"error": "rate_limited"}
    return JSONResponse(
        status_code=exc.status_code,
        content=detail,
        headers=exc.headers or {},
    )


def _cors_allowed_origins() -> list[str]:
    """Build the CORS allow-list from env so prod hosts can be added without code changes.

    - Always include Vite dev origins (browsers treat localhost and 127.0.0.1 as distinct).
    - Include FRONTEND_BASE_URL (single prod origin used elsewhere for redirects).
    - Include any extras in CORS_ALLOWED_ORIGINS (comma-separated).
    """
    origins = {"http://localhost:5173", "http://127.0.0.1:5173"}
    frontend = (os.getenv("FRONTEND_BASE_URL") or "").strip().rstrip("/")
    if frontend:
        origins.add(frontend)
    extras = (os.getenv("CORS_ALLOWED_ORIGINS") or "").strip()
    if extras:
        for o in extras.split(","):
            o = o.strip().rstrip("/")
            if o:
                origins.add(o)
    return sorted(origins)


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(plan.router, prefix="/api/plan", tags=["plan"])
app.include_router(four_year_plan.router, prefix="/api/four-year-plan", tags=["four-year-plan"])
app.include_router(memory.router, prefix="/api/memory", tags=["memory"])
app.include_router(upload.router, prefix="/api/upload", tags=["upload"])
app.include_router(voice.router, prefix="/api/voice", tags=["voice"])
app.include_router(workday.router, prefix="/api/workday", tags=["workday"])


@app.get("/api/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}
