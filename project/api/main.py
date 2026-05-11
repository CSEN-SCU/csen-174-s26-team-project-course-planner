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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import auth, four_year_plan, memory, plan, upload, voice

app = FastAPI(title="SCU Course Planner API")

app.add_middleware(
    CORSMiddleware,
    # Browsers treat localhost and 127.0.0.1 as different origins — allow both for Vite dev.
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
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


@app.get("/api/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}
