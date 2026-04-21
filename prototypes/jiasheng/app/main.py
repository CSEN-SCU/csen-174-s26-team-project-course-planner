from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

from typing import Optional

from fastapi import Depends, FastAPI, Request, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from .ai_client import ai_enabled, ai_provider_label
from .db import SessionLocal, engine
from .major_requirements import fetch_major_requirements
from .models import Base, Recommendation, StudentSession
from .plan_logic import build_plan, build_plan_from_academic_progress
from .schemas import MajorRequirementsResponse, PlanRequest, PlanResponse, ProgressPlanResponse


BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"
UPLOADS_DIR = BASE_DIR / "data" / "uploads"

app = FastAPI(title="SCU Course Planner — Jiasheng Prototype")

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
def landing(request: Request):
    return templates.TemplateResponse(
        "landing.html",
        {
            "request": request,
            "ai_enabled": ai_enabled(),
            "ai_provider": ai_provider_label(),
        },
    )


@app.get("/app")
def planner(request: Request):
    return templates.TemplateResponse(
        "planner.html",
        {
            "request": request,
            "ai_enabled": ai_enabled(),
            "ai_provider": ai_provider_label(),
        },
    )


@app.post("/api/plan", response_model=PlanResponse)
async def plan(payload: PlanRequest, db: Session = Depends(get_db)) -> PlanResponse:
    parsed, recs = await build_plan(payload)

    session = StudentSession(
        major=payload.major,
        term=payload.term,
        transcript_text=payload.transcript_text,
        transcript_parsed_json=json.dumps([c.model_dump() for c in parsed], ensure_ascii=False),
        prefs_json=payload.prefs.model_dump_json(),
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    for r in recs:
        db.add(
            Recommendation(
                session_id=session.id,
                course_code=r.course.code,
                course_title=r.course.title,
                score=float(r.score),
                rationale_json=json.dumps(r.rationale, ensure_ascii=False),
            )
        )
    db.commit()

    return PlanResponse(
        session_id=session.id,
        ai_enabled=ai_enabled(),
        ai_provider=ai_provider_label(),
        parsed_courses=parsed,
        recommendations=recs,
    )


@app.get("/api/major_requirements", response_model=MajorRequirementsResponse)
async def major_requirements(url: str) -> MajorRequirementsResponse:
    mr = await fetch_major_requirements(url)
    return MajorRequirementsResponse(
        source_url=mr.source_url,
        sections=mr.sections,
        option_groups=mr.option_groups,
        notes=mr.notes,
    )


@app.post("/api/upload_progress")
async def upload_progress(file: UploadFile) -> JSONResponse:
    name = (file.filename or "").lower()
    if not name.endswith(".xlsx"):
        return JSONResponse({"error": "only_xlsx_supported"}, status_code=400)

    file_id = uuid.uuid4().hex
    dest = UPLOADS_DIR / f"{file_id}.xlsx"
    try:
        with dest.open("wb") as out:
            shutil.copyfileobj(file.file, out)
    except Exception:
        return JSONResponse({"error": "upload_failed"}, status_code=500)
    finally:
        try:
            file.file.close()
        except Exception:
            pass

    return JSONResponse({"file_id": file_id})


@app.get("/api/plan_from_progress", response_model=ProgressPlanResponse)
async def plan_from_progress(url: str, term: str = "2026 Spring", file_id: Optional[str] = None) -> ProgressPlanResponse:
    if file_id:
        progress_path = str((UPLOADS_DIR / f"{file_id}.xlsx").resolve())
    else:
        # Back-compat: convention path in repo root
        progress_path = str((BASE_DIR / "View_My_Academic_Progress.xlsx").resolve())
    data = await build_plan_from_academic_progress(
        progress_xlsx_path=progress_path,
        major_requirements_url=url,
        term=term,
    )
    return ProgressPlanResponse(
        source_progress_file=progress_path,
        major_requirements_url=url,
        completed_codes=data["completed_codes"],
        missing_major_codes=data["missing_major_codes"],
        unsatisfied_requirements=data["unsatisfied_requirements"],
        recommendations=data["recommendations"],
    )


@app.get("/api/session/{session_id}")
def get_session(session_id: int, db: Session = Depends(get_db)) -> JSONResponse:
    s = db.get(StudentSession, session_id)
    if not s:
        return JSONResponse({"error": "not_found"}, status_code=404)

    recs = (
        db.query(Recommendation)
        .filter(Recommendation.session_id == session_id)
        .order_by(Recommendation.score.desc())
        .all()
    )

    return JSONResponse(
        {
            "session": {
                "id": s.id,
                "major": s.major,
                "term": s.term,
                "created_at": s.created_at.isoformat(),
                "transcript_parsed": json.loads(s.transcript_parsed_json or "[]"),
                "prefs": json.loads(s.prefs_json or "{}"),
            },
            "recommendations": [
                {
                    "course_code": r.course_code,
                    "course_title": r.course_title,
                    "score": r.score,
                    "rationale": json.loads(r.rationale_json or "{}"),
                }
                for r in recs
            ],
        }
    )
