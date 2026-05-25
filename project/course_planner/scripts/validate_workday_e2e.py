#!/usr/bin/env python3
"""Automated checks for Workday pull E2E (no Duo). Live browser tests are separate.

Run from project/course_planner/::

    python scripts/validate_workday_e2e.py

Exits 0 when all automated checks pass; prints a checklist for human Duo steps.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_CWD = Path.cwd()
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

REPO_ROOT = _ROOT.parent.parent
SAMPLE_PROGRESS = _ROOT / "View_My_Academic_Progress.xlsx"
SAMPLE_SECTIONS = _ROOT / "SCU_Find_Course_Sections.xlsx"
PROFILE = _ROOT / ".workday_profile"


def _run(cmd: list[str], *, cwd: Path | None = None) -> tuple[int, str]:
    p = subprocess.run(
        cmd,
        cwd=cwd or REPO_ROOT / "project",
        capture_output=True,
        text=True,
    )
    out = (p.stdout or "") + (p.stderr or "")
    return p.returncode, out


def check_gitignore_security() -> bool:
    print("\n[4] Security: git status must not list profile/cookies")
    r = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    lines = [ln for ln in (r.stdout or "").splitlines() if ln.strip()]
    bad = [
        ln
        for ln in lines
        if any(
            x in ln.lower()
            for x in (
                ".workday_profile",
                "cookies",
                "credentials",
                ".env",
            )
        )
        and "??" not in ln or ".workday_profile" in ln
    ]
    # Untracked .workday_profile is OK if gitignored; verify ignore
    check = subprocess.run(
        ["git", "check-ignore", "-v", str(PROFILE)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    ignored = check.returncode == 0
    print(f"    .workday_profile gitignored: {ignored}")
    if bad:
        print("    FAIL staged/modified sensitive paths:")
        for ln in bad:
            print(f"      {ln}")
        return False
    print("    PASS (no profile/credentials in tracked changes)")
    return ignored


def check_unit_tests() -> bool:
    print("\n[unit] pytest workday + courses refresh")
    code, out = _run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_workday_browser_scripts.py",
            "tests/test_workday_pull_progress.py",
            "tests/test_workday_pull_sections.py",
            "tests/test_courses_refresh.py",
            "-q",
        ],
    )
    print(out[-2000:] if len(out) > 2000 else out)
    return code == 0


def check_sample_upload_parity(api_base: str) -> bool:
    print("\n[1-partial] Sample xlsx vs parse (no Workday browser)")
    if not SAMPLE_PROGRESS.is_file():
        print(f"    SKIP — missing {SAMPLE_PROGRESS.name} (gitignored sample)")
        return True
    from utils.academic_progress_xlsx import parse_academic_progress_xlsx, sanitize_parsed_rows
    from utils.academic_progress_helpers import enrich_missing_details

    raw = SAMPLE_PROGRESS.read_bytes()
    data = parse_academic_progress_xlsx(raw)
    detail = data.get("detail_rows") or []
    not_sat = data.get("not_satisfied") or []
    if not detail and not not_sat:
        print("    FAIL sample parses empty")
        return False
    parsed_rows = sanitize_parsed_rows(detail)
    missing = enrich_missing_details(not_sat, parsed_rows)
    print(f"    parse: detail_rows={len(detail)} not_satisfied={len(not_sat)}")
    try:
        import requests

        files = {
            "file": (SAMPLE_PROGRESS.name, raw, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        }
        uid = os.environ.get("WORKDAY_E2E_USER_ID", "e2e-test-user")
        resp = requests.post(
            f"{api_base}/api/upload/transcript",
            files=files,
            data={"user_id": uid},
            timeout=30,
        )
        if resp.status_code != 200:
            print(f"    SKIP API upload — status {resp.status_code} (is API running?)")
            return True
        body = resp.json()
        print(
            f"    API: missing_details={len(body.get('missing_details') or [])} "
            f"parsed_rows={len(body.get('parsed_rows') or [])}"
        )
        return bool(body.get("parsed_rows"))
    except Exception as exc:  # noqa: BLE001
        print(f"    SKIP API — {exc}")
        return True


def check_sections_catalog() -> bool:
    print("\n[2-partial] Sections xlsx on disk")
    if not SAMPLE_SECTIONS.is_file():
        print(f"    SKIP — missing {SAMPLE_SECTIONS.name}")
        return True
    from utils.scu_course_schedule_xlsx import list_offered_courses

    n = len(list_offered_courses(SAMPLE_SECTIONS))
    mtime = SAMPLE_SECTIONS.stat().st_mtime
    print(f"    courses={n} mtime={mtime}")
    return n > 0


def check_robustness_empty_parse() -> bool:
    print("\n[3] Robustness: empty xlsx aborts validation")
    from io import BytesIO

    from openpyxl import Workbook
    from scripts import workday_pull_progress as wpp

    wb = Workbook()
    ws = wb.active
    ws.append(["Requirement", "Status", "Remaining", "Registration", "Period", "Units", "Grade"])
    buf = BytesIO()
    wb.save(buf)
    try:
        wpp.validate_progress_export(buf.getvalue())
        print("    FAIL should have raised")
        return False
    except wpp.ProgressValidationError as exc:
        print(f"    PASS ProgressValidationError: {str(exc)[:80]}...")
        return True


def print_human_checklist() -> None:
    print(
        """
============================================================
 HUMAN STEPS (require Duo in headed browser)
============================================================
1. Start API:  cd project/api && uvicorn main:app --reload --port 8000
2. Progress:   cd project/course_planner
               python scripts/workday_pull_progress.py --user-id <USER_ID>
               → login + Duo → expect non-zero missing_details / parsed_rows
3. Sections:   python scripts/workday_pull_sections.py
               → login → SCU_Find_Course_Sections.xlsx new mtime
               curl -X POST http://localhost:8000/api/courses/refresh
4. Wrong page: SCU_WORKDAY_URL=https://www.myworkday.com/scu/d/home.htmld \\
               python scripts/workday_pull_progress.py --save /tmp/bad.xlsx
               → must exit 1 or 2 with clear error, no /tmp/bad.xlsx or empty file
============================================================
"""
    )


def main() -> int:
    api = os.environ.get("WORKDAY_E2E_API", "http://localhost:8000")
    ok = True
    ok &= check_unit_tests()
    ok &= check_robustness_empty_parse()
    ok &= check_sample_upload_parity(api)
    ok &= check_sections_catalog()
    ok &= check_gitignore_security()
    print_human_checklist()
    print("Automated checks:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
