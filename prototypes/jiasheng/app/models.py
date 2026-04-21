from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class StudentSession(Base):
    __tablename__ = "student_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    major: Mapped[str] = mapped_column(String(256), nullable=False)
    term: Mapped[str] = mapped_column(String(64), nullable=False)

    transcript_text: Mapped[str] = mapped_column(Text, nullable=False)
    transcript_parsed_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")

    prefs_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    recommendations: Mapped[list["Recommendation"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class Recommendation(Base):
    __tablename__ = "recommendations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("student_sessions.id", ondelete="CASCADE"), index=True)

    course_code: Mapped[str] = mapped_column(String(64), nullable=False)
    course_title: Mapped[str] = mapped_column(String(512), nullable=False)

    score: Mapped[float] = mapped_column(Float, nullable=False)
    rationale_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    session: Mapped[StudentSession] = relationship(back_populates="recommendations")
