"""Course-plan quality evaluation harness.

- ``scorers``  — deterministic rule-based scorers (R1-R6, injection safety)
- ``scenarios`` — eval inputs (missing_details + preference) + context loader
- ``run_eval``  — execute an engine over the scenarios and print a report
"""
from evals.scorers import PlanScore, ScoreResult, score_plan  # noqa: F401

__all__ = ["score_plan", "PlanScore", "ScoreResult"]
