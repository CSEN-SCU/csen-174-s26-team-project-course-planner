from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProfessorRating:
    name: str
    rating: float
    source: str = "manual"


def _norm_name(name: str) -> str:
    return " ".join(name.strip().lower().split())


def load_prof_ratings(base_dir: Path) -> dict[str, ProfessorRating]:
    """
    Optional override file to sort instructors by quality (RMP-style).

    Supported file:
      - data/prof_ratings.json

    Format:
      {
        "Wendy Donohoe": {"rating": 4.2, "source": "rmp"},
        "John Lord": {"rating": 3.8}
      }
    """
    path = base_dir / "data" / "prof_ratings.json"
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(raw, dict):
        return {}

    out: dict[str, ProfessorRating] = {}
    for k, v in raw.items():
        if not isinstance(k, str):
            continue
        if isinstance(v, (int, float)):
            rating = float(v)
            source = "manual"
        elif isinstance(v, dict):
            r = v.get("rating")
            if not isinstance(r, (int, float)):
                continue
            rating = float(r)
            source = str(v.get("source") or "manual")
        else:
            continue
        out[_norm_name(k)] = ProfessorRating(name=k.strip(), rating=rating, source=source)

    return out

