"""Zero-review RMP profiles must not surface as a fake "0.0★" rating.

Production bug: RMP returns overall_rating=0.0 (not None) for professors with
no reviews, and _prof_to_dict passed that through verbatim, so the UI rendered
"0.0★ instructor quality" (e.g. AMTH 118 / Francisco Alvarez). A zero-review
profile should be treated as "rating unavailable" so the UI shows
"No Rate My Professor rating" instead.
"""

from __future__ import annotations

from types import SimpleNamespace

from agents.professor_agent import _prof_to_dict


def _prof(name, *, rating, difficulty, num_ratings, wta=None):
    return SimpleNamespace(
        name=name,
        overall_rating=rating,
        level_of_difficulty=difficulty,
        num_ratings=num_ratings,
        percent_take_again=wta,
    )


def test_zero_review_professor_rating_is_nulled():
    """num_ratings=0 → rating/difficulty become None (not 0.0)."""
    out = _prof_to_dict(_prof("Francisco Alvarez", rating=0.0, difficulty=0.0, num_ratings=0))
    assert out["rating"] is None
    assert out["difficulty"] is None
    assert out["would_take_again"] == "N/A"


def test_missing_num_ratings_is_nulled():
    """num_ratings=None (unknown) is treated the same as zero reviews."""
    out = _prof_to_dict(_prof("Nobody", rating=0.0, difficulty=2.0, num_ratings=None))
    assert out["rating"] is None
    assert out["difficulty"] is None


def test_real_rating_is_preserved():
    """A professor with reviews keeps their real numbers."""
    out = _prof_to_dict(
        _prof("Shoba Krishnan", rating=4.4, difficulty=3.8, num_ratings=37, wta=88.0)
    )
    assert out["rating"] == 4.4
    assert out["difficulty"] == 3.8
    assert out["would_take_again"] == "88%"


def test_real_rating_with_zero_score_but_reviews_is_kept():
    """A genuinely low rating (with reviews) is NOT nulled — only no-review is."""
    out = _prof_to_dict(_prof("Tough Grader", rating=1.2, difficulty=4.9, num_ratings=15))
    assert out["rating"] == 1.2
    assert out["difficulty"] == 4.9
