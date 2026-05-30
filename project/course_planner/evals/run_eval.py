"""Eval runner — execute an engine over the scenarios and print a report.

Usage (from project/course_planner/):

    python -m evals.run_eval --engine legacy
    python -m evals.run_eval --engine multi_agent
    python -m evals.run_eval --engine both          # A/B compare

This DOES call the real Gemini model (set GEMINI_API_KEY). Use a small
scenario set; each scenario is one or more LLM round-trips. The scorers
themselves are deterministic and offline.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Callable

from evals.scenarios import default_scenarios, scenario_context
from evals.scorers import score_plan


def _empty_plan(engine_label: str) -> dict[str, Any]:
    """Return a clean empty plan with a meta.validation block so scorers
    correctly classify it as "nothing to plan" rather than "broken
    engine"."""
    return {
        "recommended": [],
        "total_units": 0,
        "advice": "",
        "assistant_reply": "",
        "meta": {"validation": {"engine": engine_label}},
    }


def _legacy_engine(scenario) -> dict[str, Any]:
    from agents.planning_agent import run_planning_agent

    if not scenario.missing_details:
        return _empty_plan("legacy")
    return run_planning_agent(scenario.missing_details, scenario.user_preference)


def _multi_agent_engine(scenario) -> dict[str, Any]:
    from agents.multi_agent import run_multi_agent_plan

    if not scenario.missing_details:
        return _empty_plan("multi_agent")
    return run_multi_agent_plan(scenario.missing_details, scenario.user_preference)


def _constrained_v2_engine(scenario) -> dict[str, Any]:
    from agents.planning_agent_v2 import run_constrained_planner

    if not scenario.missing_details:
        return _empty_plan("constrained_v2")
    return run_constrained_planner(scenario.missing_details, scenario.user_preference)


def _llm_engine(scenario) -> dict[str, Any]:
    from agents.planning_agent_llm import run_llm_planner

    if not scenario.missing_details:
        return _empty_plan("llm_select")
    return run_llm_planner(scenario.missing_details, scenario.user_preference)


ENGINES: dict[str, Callable] = {
    "legacy": _legacy_engine,
    "multi_agent": _multi_agent_engine,
    "constrained_v2": _constrained_v2_engine,
    "llm": _llm_engine,
}


def run_engine(engine_name: str) -> dict[str, Any]:
    engine = ENGINES[engine_name]
    scenarios = default_scenarios()
    rows: list[dict[str, Any]] = []
    for sc in scenarios:
        try:
            plan = engine(sc)
            err = None
        except Exception as e:  # noqa: BLE001
            plan, err = {"recommended": [], "total_units": 0}, str(e)
        ctx = scenario_context(sc)
        ps = score_plan(plan, ctx)
        rows.append({
            "scenario": sc.name,
            "error": err,
            "mean_score": round(ps.mean, 3),
            "pass_rate": round(ps.pass_rate, 3),
            "results": ps.as_dict()["results"],
            "n_recommended": len(plan.get("recommended") or []),
        })
    overall = (
        sum(r["mean_score"] for r in rows) / len(rows) if rows else 0.0
    )
    return {"engine": engine_name, "overall_mean": round(overall, 3), "scenarios": rows}


def _print_report(report: dict[str, Any]) -> None:
    print(f"\n=== ENGINE: {report['engine']}  (overall mean {report['overall_mean']}) ===")
    for row in report["scenarios"]:
        flag = "ERR" if row["error"] else ""
        print(f"\n  {row['scenario']:22} mean={row['mean_score']:.3f} "
              f"pass={row['pass_rate']:.2f} n={row['n_recommended']} {flag}")
        if row["error"]:
            print(f"    error: {row['error']}")
        for res in row["results"]:
            mark = "✓" if res["passed"] else "✗"
            print(f"      {mark} {res['name']:20} {res['score']:.2f}  {res['detail']}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Course-plan quality eval")
    ap.add_argument(
        "--engine",
        choices=["legacy", "multi_agent", "constrained_v2", "llm", "all", "both"],
        default="constrained_v2",
    )
    ap.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    args = ap.parse_args(argv)

    if args.engine == "all":
        engines = ["legacy", "multi_agent", "constrained_v2", "llm"]
    elif args.engine == "both":
        engines = ["legacy", "constrained_v2"]
    else:
        engines = [args.engine]
    reports = [run_engine(e) for e in engines]

    if args.json:
        print(json.dumps(reports, indent=2, ensure_ascii=False))
    else:
        for r in reports:
            _print_report(r)
        if len(reports) >= 2:
            print("\n=== A/B summary ===")
            for r in reports:
                print(f"  {r['engine']:18} overall_mean={r['overall_mean']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
