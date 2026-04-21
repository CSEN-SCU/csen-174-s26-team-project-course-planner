from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class Preferences(BaseModel):
    quality_weight: int = Field(60, ge=0, le=100)
    workload_weight: int = Field(60, ge=0, le=100)  # higher => more willing to tolerate workload
    progress_weight: int = Field(70, ge=0, le=100)

    avoid_evening: bool = False  # after 17:00 start
    online_only: bool = False


class PlanRequest(BaseModel):
    major: str = Field(..., min_length=1, max_length=256)
    term: str = Field("2026 Spring", min_length=1, max_length=64)
    transcript_text: str = Field(..., min_length=1)
    prefs: Preferences = Field(default_factory=Preferences)


class ParsedCourse(BaseModel):
    code: str
    title: Optional[str] = None
    term: Optional[str] = None
    grade: Optional[str] = None
    units: Optional[float] = None
    attempted_units: Optional[float] = None
    earned_units: Optional[float] = None
    points: Optional[float] = None


class OfferingOut(BaseModel):
    code: str
    title: str
    term: str
    units: int
    prereqs: list[str]
    schedule: str
    instructors: list[str] = Field(default_factory=list)
    quality: float
    workload: float
    status: Literal["eligible", "ineligible", "unknown"]
    missing_prereqs: list[str]


class RecommendationOut(BaseModel):
    course: OfferingOut
    score: float
    rationale: dict[str, Any]


class PlanResponse(BaseModel):
    session_id: int
    ai_enabled: bool
    ai_provider: str
    parsed_courses: list[ParsedCourse]
    recommendations: list[RecommendationOut]


class MajorRequirementsResponse(BaseModel):
    source_url: str
    sections: dict[str, list[str]]
    option_groups: list[list[str]] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ProgressPlanItem(BaseModel):
    code: str
    title: str
    term: str
    units: int
    schedule: str
    tags: Optional[str] = None
    instructors: list[str] = Field(default_factory=list)
    why: str


class ProgressPlanResponse(BaseModel):
    source_progress_file: str
    major_requirements_url: str
    completed_codes: list[str]
    missing_major_codes: list[str]
    unsatisfied_requirements: list[str]
    recommendations: list[ProgressPlanItem]
