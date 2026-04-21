from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from .config import DATABASE_URL


def _ensure_sqlite_dir(url: str) -> None:
    if not url.startswith("sqlite:///"):
        return
    # sqlite:////abs/path -> Path after scheme
    db_path = url.replace("sqlite:///", "", 1)
    # If relative, sqlite treats it relative to cwd; we still mkdir parent if present
    p = Path(db_path)
    if not p.is_absolute():
        return
    p.parent.mkdir(parents=True, exist_ok=True)


_ensure_sqlite_dir(DATABASE_URL)

connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

__all__ = ["engine", "SessionLocal"]
