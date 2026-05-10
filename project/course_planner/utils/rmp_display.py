"""Shared helpers for displaying RateMyProfessor rows in the UI."""

from __future__ import annotations

from typing import Any


def professors_sorted_by_rating(profs: list[Any]) -> list[dict]:
    """Return professor dicts sorted by overall rating descending; missing ratings last."""
    rows = [p for p in profs if isinstance(p, dict)]

    def key(d: dict) -> float:
        r = d.get("rating")
        try:
            return float(r)
        except (TypeError, ValueError):
            return float("-inf")

    return sorted(rows, key=key, reverse=True)
