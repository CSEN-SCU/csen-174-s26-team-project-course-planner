#!/usr/bin/env python3
"""Scrape SCU Bulletin → one Markdown file per popular major.

Usage (from project/course_planner/):
    python3 scripts/scrape_major_requirements.py
    python3 scripts/scrape_major_requirements.py --major csen --major ecen

Writes:
    data/majors/<major_id>.md     — requirements + per-course prerequisites
    data/majors/index.json        — manifest for agent lookup
    data/major_requirements.json  — compact index (backward compatible)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

_SCRIPT_ROOT = Path(__file__).resolve().parent.parent
if str(_SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_ROOT))

from utils.bulletin_major_scraper import render_major_markdown, scrape_bulletin_major

_MAJORS_DIR = _SCRIPT_ROOT / "data" / "majors"
_INDEX_PATH = _MAJORS_DIR / "index.json"
_LEGACY_JSON = _SCRIPT_ROOT / "data" / "major_requirements.json"

# Popular SCU majors — bulletin chapter URLs (2025-26).
POPULAR_MAJORS: dict[str, dict[str, Any]] = {
    # ── School of Engineering (chapter 5) ─────────────────────────────────────
    "csen": {
        "id": "csen",
        "name": "Computer Science and Engineering",
        "url": "https://www.scu.edu/bulletin/undergraduate/chapter-5-school-of-engineering/computer-science-and-engineering.html",
        "school": "engineering",
        "default_subject": "CSEN",
        "subject_prefixes": ["CSEN", "COEN", "ENGR", "ECEN", "MATH", "AMTH", "PHYS", "CHEM", "ENGL"],
        "primary_bs_marker": "Bachelor of Science in Computer Science and Engineering",
        "detect_patterns": [
            "computer science and engineering",
            "csen/coen",
            "csen major",
            "coen major",
        ],
        "senior_design_sequence": ["CSEN 192", "CSEN 194", "CSEN 195", "CSEN 196"],
        "senior_design_final_year_only": True,
    },
    "wede": {
        "id": "wede",
        "name": "Web Design and Engineering",
        "url": "https://www.scu.edu/bulletin/undergraduate/chapter-5-school-of-engineering/computer-science-and-engineering.html",
        "school": "engineering",
        "default_subject": "CSEN",
        "subject_prefixes": ["CSEN", "ENGR", "ARTS", "COMM", "SOCI", "MATH", "AMTH", "ENGL"],
        "primary_bs_marker": "Bachelor of Science in Web Design and Engineering",
        "detect_patterns": ["web design and engineering", "wede"],
        "senior_design_sequence": ["CSEN 192", "CSEN 194", "CSEN 195", "CSEN 196"],
        "senior_design_final_year_only": True,
    },
    "ecen": {
        "id": "ecen",
        "name": "Electrical and Computer Engineering",
        "url": "https://www.scu.edu/bulletin/undergraduate/chapter-5-school-of-engineering/electrical-and-computer-engineering.html",
        "school": "engineering",
        "default_subject": "ECEN",
        "subject_prefixes": ["ECEN", "ELEN", "CSEN", "ENGR", "MECH", "MATH", "AMTH", "PHYS", "CHEM", "CSCI"],
        "detect_patterns": [
            "electrical and computer engineering",
            "ecen major",
        ],
        "senior_design_sequence": ["ECEN 192", "ECEN 194", "ECEN 195", "ECEN 196"],
        "senior_design_final_year_only": True,
        "tracks": [
            {"name": "Electrical Engineering", "marker": "Major in Electrical Engineering"},
            {
                "name": "Electrical and Computer Engineering",
                "marker": "Major in Electrical and Computer Engineering",
            },
        ],
    },
    "elen": {
        "id": "elen",
        "name": "Electrical Engineering",
        "url": "https://www.scu.edu/bulletin/undergraduate/chapter-5-school-of-engineering/electrical-and-computer-engineering.html",
        "school": "engineering",
        "default_subject": "ECEN",
        "subject_prefixes": ["ECEN", "ELEN", "CSEN", "ENGR", "MECH", "MATH", "AMTH", "PHYS", "CHEM"],
        "detect_patterns": ["electrical engineering", "elen major"],
        "senior_design_sequence": ["ECEN 192", "ECEN 194", "ECEN 195", "ECEN 196"],
        "senior_design_final_year_only": True,
        "tracks": [{"name": "Electrical Engineering", "marker": "Major in Electrical Engineering"}],
    },
    "mech": {
        "id": "mech",
        "name": "Mechanical Engineering",
        "url": "https://www.scu.edu/bulletin/undergraduate/chapter-5-school-of-engineering/mechanical-engineering.html",
        "school": "engineering",
        "default_subject": "MECH",
        "subject_prefixes": ["MECH", "ENGR", "MATH", "AMTH", "PHYS", "CHEM", "ECEN"],
        "detect_patterns": ["mechanical engineering", "mech major"],
        "senior_design_sequence": ["MECH 192", "MECH 194", "MECH 195", "MECH 196"],
        "senior_design_final_year_only": True,
    },
    "bioe": {
        "id": "bioe",
        "name": "Bioengineering",
        "url": "https://www.scu.edu/bulletin/undergraduate/chapter-5-school-of-engineering/bioengineering.html",
        "school": "engineering",
        "default_subject": "BIOE",
        "subject_prefixes": ["BIOE", "ENGR", "MATH", "AMTH", "PHYS", "CHEM"],
        "detect_patterns": ["bioengineering", "bioe major"],
        "senior_design_sequence": [],
        "senior_design_final_year_only": True,
    },
    "ceng": {
        "id": "ceng",
        "name": "Civil, Environmental, and Sustainable Engineering",
        "url": "https://www.scu.edu/bulletin/undergraduate/chapter-5-school-of-engineering/civil-environmental-and-sustainable-engineering.html",
        "school": "engineering",
        "default_subject": "CENG",
        "subject_prefixes": ["CENG", "ENGR", "ECEN", "MATH", "AMTH", "PHYS", "CHEM"],
        "detect_patterns": ["civil engineering", "civil, environmental", "ceng major"],
        "senior_design_sequence": ["CENG 192A", "CENG 193", "CENG 194"],
        "senior_design_final_year_only": True,
    },
    # ── Leavey School of Business (chapter 4) ───────────────────────────────────
    "fnce": {
        "id": "fnce",
        "name": "Finance",
        "url": "https://www.scu.edu/bulletin/undergraduate/chapter-4-leavey-school-of-business/finance.html",
        "school": "business",
        "default_subject": "FNCE",
        "subject_prefixes": ["FNCE", "MATH", "OMIS", "ECON", "ACTG"],
        "detect_patterns": ["finance major", "majoring in finance"],
        "senior_design_sequence": [],
        "senior_design_final_year_only": False,
    },
    "actg": {
        "id": "actg",
        "name": "Accounting",
        "url": "https://www.scu.edu/bulletin/undergraduate/chapter-4-leavey-school-of-business/accounting.html",
        "school": "business",
        "default_subject": "ACTG",
        "subject_prefixes": ["ACTG", "OMIS", "BUSN"],
        "detect_patterns": ["accounting major", "majoring in accounting"],
        "senior_design_sequence": [],
        "senior_design_final_year_only": False,
        "tracks": [
            {"name": "Accounting", "marker": "Major in Accounting"},
            {"name": "Accounting and Information Systems", "marker": "Major in Accounting and Information Systems"},
        ],
    },
    "econ": {
        "id": "econ",
        "name": "Economics",
        "url": "https://www.scu.edu/bulletin/undergraduate/chapter-4-leavey-school-of-business/economics.html",
        "school": "business",
        "default_subject": "ECON",
        "subject_prefixes": ["ECON", "MATH", "OMIS", "AMTH"],
        "detect_patterns": ["economics major", "majoring in economics"],
        "senior_design_sequence": [],
        "senior_design_final_year_only": False,
    },
    "mktg": {
        "id": "mktg",
        "name": "Marketing",
        "url": "https://www.scu.edu/bulletin/undergraduate/chapter-4-leavey-school-of-business/marketing.html",
        "school": "business",
        "default_subject": "MKTG",
        "subject_prefixes": ["MKTG", "OMIS", "COMM"],
        "detect_patterns": ["marketing major", "majoring in marketing"],
        "senior_design_sequence": [],
        "senior_design_final_year_only": False,
    },
    "mgmt": {
        "id": "mgmt",
        "name": "Management",
        "url": "https://www.scu.edu/bulletin/undergraduate/chapter-4-leavey-school-of-business/management.html",
        "school": "business",
        "default_subject": "MGMT",
        "subject_prefixes": ["MGMT", "OMIS", "ECON"],
        "detect_patterns": ["management major", "majoring in management"],
        "senior_design_sequence": [],
        "senior_design_final_year_only": False,
    },
    "omis": {
        "id": "omis",
        "name": "Management Information Systems",
        "url": "https://www.scu.edu/bulletin/undergraduate/chapter-4-leavey-school-of-business/information-systems-analytics.html",
        "school": "business",
        "default_subject": "OMIS",
        "subject_prefixes": ["OMIS", "ACTG", "CSEN", "ECON"],
        "detect_patterns": [
            "management information systems",
            "mis major",
            "omis major",
        ],
        "senior_design_sequence": [],
        "senior_design_final_year_only": False,
        "tracks": [{"name": "Management Information Systems", "marker": "Major in Management Information Systems"}],
    },
    "bsan": {
        "id": "bsan",
        "name": "Business Analytics",
        "url": "https://www.scu.edu/bulletin/undergraduate/chapter-4-leavey-school-of-business/information-systems-analytics.html",
        "school": "business",
        "default_subject": "OMIS",
        "subject_prefixes": ["OMIS", "MATH", "ECON", "CSEN", "ACTG"],
        "detect_patterns": ["business analytics", "bsan"],
        "senior_design_sequence": [],
        "senior_design_final_year_only": False,
        "tracks": [{"name": "Business Analytics", "marker": "Major in Business Analytics"}],
    },
    # ── College of Arts & Sciences (chapter 3) ──────────────────────────────────
    "csci": {
        "id": "csci",
        "name": "Computer Science",
        "url": "https://www.scu.edu/bulletin/undergraduate/chapter-3-college-of-arts-and-sciences/mathematics-and-computer-science.html",
        "school": "arts_sciences",
        "default_subject": "CSCI",
        "subject_prefixes": ["CSCI", "MATH", "CSEN", "ECEN", "PHYS", "CHEM"],
        "detect_patterns": [
            "computer science major",
            "major in computer science",
            "mathematics and computer science",
        ],
        "senior_design_sequence": [],
        "senior_design_final_year_only": False,
        "tracks": [{"name": "Computer Science", "marker": "Major in Computer Science"}],
    },
    "math": {
        "id": "math",
        "name": "Mathematics",
        "url": "https://www.scu.edu/bulletin/undergraduate/chapter-3-college-of-arts-and-sciences/mathematics-and-computer-science.html",
        "school": "arts_sciences",
        "default_subject": "MATH",
        "subject_prefixes": ["MATH", "AMTH", "CSCI"],
        "detect_patterns": ["mathematics major", "major in mathematics"],
        "senior_design_sequence": [],
        "senior_design_final_year_only": False,
        "tracks": [{"name": "Mathematics", "marker": "Major in Mathematics"}],
    },
    "psyc": {
        "id": "psyc",
        "name": "Psychology",
        "url": "https://www.scu.edu/bulletin/undergraduate/chapter-3-college-of-arts-and-sciences/psychology.html",
        "school": "arts_sciences",
        "default_subject": "PSYC",
        "subject_prefixes": ["PSYC", "MATH", "SOCI"],
        "detect_patterns": ["psychology major", "majoring in psychology"],
        "senior_design_sequence": [],
        "senior_design_final_year_only": False,
    },
    "biol": {
        "id": "biol",
        "name": "Biology",
        "url": "https://www.scu.edu/bulletin/undergraduate/chapter-3-college-of-arts-and-sciences/biology.html",
        "school": "arts_sciences",
        "default_subject": "BIOL",
        "subject_prefixes": ["BIOL", "CHEM", "PHYS", "MATH"],
        "detect_patterns": ["biology major", "majoring in biology"],
        "senior_design_sequence": [],
        "senior_design_final_year_only": False,
    },
}


def _write_legacy_json(index_entries: list[dict[str, Any]]) -> None:
    """Keep major_requirements.json as a compact manifest for older code paths."""
    majors: dict[str, Any] = {}
    for entry in index_entries:
        mid = entry["major_id"]
        majors[mid] = {
            "id": mid,
            "name": entry["name"],
            "school": entry["school"],
            "detect_patterns": entry["detect_patterns"],
            "required_courses": entry.get("required_courses") or [],
            "senior_design_sequence": entry.get("senior_design_sequence") or [],
            "senior_design_final_year_only": entry.get("senior_design_final_year_only", False),
            "markdown_path": entry["markdown_path"],
        }
    payload = {
        "version": "2025-26",
        "source": "SCU Undergraduate Bulletin — per-major markdown in data/majors/",
        "majors": majors,
        "prerequisites": {},
        "course_aliases": {
            "CSEN 21": ["ECEN 21"],
            "ECEN 21": ["CSEN 21"],
            "CSEN 194": ["COEN 194", "ENGR 194"],
            "CSEN 195": ["COEN 195", "ENGR 195"],
            "CSEN 196": ["COEN 196", "ENGR 196"],
            "COEN 194": ["CSEN 194", "ENGR 194"],
            "COEN 195": ["CSEN 195", "ENGR 195"],
            "COEN 196": ["CSEN 196", "ENGR 196"],
        },
    }
    with _LEGACY_JSON.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape SCU Bulletin majors to Markdown")
    parser.add_argument("--major", action="append", dest="majors", help="Major id (repeatable)")
    args = parser.parse_args()
    targets = args.majors or list(POPULAR_MAJORS.keys())

    _MAJORS_DIR.mkdir(parents=True, exist_ok=True)
    index_entries: list[dict[str, Any]] = []

    for major_id in targets:
        meta = POPULAR_MAJORS.get(major_id)
        if not meta:
            print(f"Unknown major {major_id!r}, skip.", file=sys.stderr)
            continue
        print(f"Scraping {major_id} …")
        try:
            scraped = scrape_bulletin_major(meta)
            md = render_major_markdown(scraped)
            out_path = _MAJORS_DIR / f"{major_id}.md"
            out_path.write_text(md, encoding="utf-8")
            rel = f"majors/{major_id}.md"
            all_required: list[str] = []
            for tr in scraped.tracks:
                all_required.extend(tr.required_courses)
            seen: set[str] = set()
            deduped: list[str] = []
            for c in all_required:
                if c not in seen:
                    seen.add(c)
                    deduped.append(c)
            index_entries.append(
                {
                    "major_id": major_id,
                    "name": scraped.name,
                    "school": scraped.school,
                    "bulletin_url": scraped.bulletin_url,
                    "markdown_path": rel,
                    "detect_patterns": scraped.detect_patterns,
                    "required_courses": deduped,
                    "senior_design_sequence": scraped.senior_design_sequence,
                    "senior_design_final_year_only": scraped.senior_design_final_year_only,
                    "course_count": len(scraped.courses),
                }
            )
            print(f"  → {out_path} ({len(scraped.courses)} courses, {len(deduped)} required codes)")
        except Exception as exc:  # noqa: BLE001
            print(f"  FAILED {major_id}: {exc}", file=sys.stderr)
        time.sleep(0.6)

    index_payload = {
        "version": "2025-26",
        "scraped_at": time.strftime("%Y-%m-%d"),
        "majors": index_entries,
    }
    with _INDEX_PATH.open("w", encoding="utf-8") as f:
        json.dump(index_payload, f, indent=2, ensure_ascii=False)
        f.write("\n")

    _write_legacy_json(index_entries)
    print(f"\nWrote {len(index_entries)} majors to {_MAJORS_DIR}/")
    print(f"Index: {_INDEX_PATH}")
    print(f"Legacy manifest: {_LEGACY_JSON}")


if __name__ == "__main__":
    main()
