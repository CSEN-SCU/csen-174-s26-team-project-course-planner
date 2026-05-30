"""Run synthetic grade-level students through an engine and analyze quality.

This is the analysis harness behind the grade-level tests. For each
(major, grade) it builds a synthetic student, runs the constrained_v2
engine OFFLINE (course selection is deterministic; only prose needs an
LLM, which we don't assert on), scores the plan with the existing
deterministic scorers, and layers on grade-appropriateness checks the
generic scorers don't cover:

  * no_completed_recourse — a course the student already finished must
    never be recommended again (regression guard for completed-code
    filtering).
  * freshman_no_senior_design — a freshman (0 completed) must not be
    handed Senior Design (CSEN 19x); those have deep prerequisites.
  * within_hard_unit_cap — total units must never exceed 20 (AGENTS.md).

Run (from project/course_planner/):
    python -m evals.grade_level_eval                 # table for csen
    python -m evals.grade_level_eval --major ecen mech
    python -m evals.grade_level_eval --json
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from typing import Any

from agents.planning_agent_v2 import run_constrained_planner
from evals.scenarios import load_context
from evals.scorers import score_plan
from evals.synthetic_students import SyntheticStudent, all_grades, make_student

_SENIOR_DESIGN_RE = re.compile(r"\b(?:CSEN|COEN|ECEN|ELEN|MECH|ENGR)\s*19[2-9]", re.IGNORECASE)
_HARD_UNIT_CAP = 20


@dataclass
class GradeFinding:
    name: str
    passed: bool
    detail: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


@dataclass
class GradeReport:
    major_id: str
    grade: str
    n_recommended: int
    total_units: int
    mean_score: float
    findings: list[GradeFinding] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        return all(f.passed for f in self.findings)

    def as_dict(self) -> dict[str, Any]:
        return {
            "major_id": self.major_id,
            "grade": self.grade,
            "n_recommended": self.n_recommended,
            "total_units": self.total_units,
            "mean_score": round(self.mean_score, 3),
            "findings": [f.as_dict() for f in self.findings],
        }


def _recommended_codes(plan: dict[str, Any]) -> list[str]:
    return [
        str(r.get("course", "")).strip().upper()
        for r in (plan.get("recommended") or [])
        if r.get("course")
    ]


def _grade_findings(student: SyntheticStudent, plan: dict[str, Any]) -> list[GradeFinding]:
    codes = _recommended_codes(plan)
    completed = {c.strip().upper() for c in student.completed_course_codes}

    # 1. No completed course re-recommended.
    repeats = sorted(set(codes) & completed)
    findings = [
        GradeFinding(
            "no_completed_recourse",
            not repeats,
            "none" if not repeats else f"re-recommended completed: {repeats}",
        )
    ]

    # 2. Freshman must not be handed Senior Design.
    if student.grade == "freshman":
        sd = [c for c in codes if _SENIOR_DESIGN_RE.search(c)]
        findings.append(
            GradeFinding(
                "freshman_no_senior_design",
                not sd,
                "none" if not sd else f"senior design for freshman: {sd}",
            )
        )

    # 3. Hard unit cap.
    try:
        total = int(plan.get("total_units") or 0)
    except (TypeError, ValueError):
        total = 0
    findings.append(
        GradeFinding(
            "within_hard_unit_cap",
            total <= _HARD_UNIT_CAP,
            f"{total}u (cap {_HARD_UNIT_CAP})",
        )
    )
    return findings


def evaluate_student(major_id: str, grade: str) -> GradeReport:
    """Build a synthetic student, run the engine offline, score + analyze."""
    student = make_student(major_id, grade)
    # Some majors define requirements by upper-division unit counts rather
    # than specific course codes (e.g. the language majors), so a
    # higher-grade student can have an empty remaining-requirement list.
    # That is a valid "nothing left to plan" state, not an engine error —
    # report it as an empty, all-pass plan instead of crashing the sweep.
    if not student.missing_details:
        return GradeReport(
            major_id=major_id,
            grade=grade,
            n_recommended=0,
            total_units=0,
            mean_score=1.0,
            findings=[GradeFinding("nothing_to_plan", True, "no remaining requirements")],
        )
    plan = run_constrained_planner(
        student.missing_details,
        "balanced quarter, stay on track to graduate",
        completed_course_codes=student.completed_course_codes,
    )
    ctx = dict(load_context())
    ctx["missing_details"] = student.missing_details
    ps = score_plan(plan, ctx)
    return GradeReport(
        major_id=major_id,
        grade=grade,
        n_recommended=len(plan.get("recommended") or []),
        total_units=int(plan.get("total_units") or 0),
        mean_score=ps.mean,
        findings=_grade_findings(student, plan),
    )


def evaluate_major(major_id: str) -> list[GradeReport]:
    return [evaluate_student(major_id, g) for g in all_grades()]


def _print_report(reports: list[GradeReport]) -> None:
    for r in reports:
        print(
            f"\n  {r.major_id} · {r.grade:10} "
            f"n={r.n_recommended} units={r.total_units} mean_score={r.mean_score:.3f}"
        )
        for f in r.findings:
            mark = "✓" if f.passed else "✗"
            print(f"      {mark} {f.name:26} {f.detail}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Grade-level recommendation eval")
    ap.add_argument("--major", nargs="+", default=["csen"], help="major id(s)")
    ap.add_argument("--json", action="store_true", help="emit JSON")
    args = ap.parse_args(argv)

    all_reports: list[GradeReport] = []
    for mid in args.major:
        all_reports.extend(evaluate_major(mid))

    if args.json:
        print(json.dumps([r.as_dict() for r in all_reports], indent=2, ensure_ascii=False))
    else:
        _print_report(all_reports)
        failed = [r for r in all_reports if not r.all_passed]
        print(f"\n=== {len(all_reports) - len(failed)}/{len(all_reports)} grade reports clean ===")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
