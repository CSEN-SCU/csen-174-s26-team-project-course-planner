#!/usr/bin/env python3
"""Scrape **all** SCU undergraduate majors from the Bulletin → Markdown.

Extends ``scrape_major_requirements.py``. The hand-curated majors in
``POPULAR_MAJORS`` keep their tuned metadata (detect_patterns,
senior_design_sequence, tracks). Every *additional* degree-granting major is
listed in the authoritative ``_DISCOVERABLE_MAJORS`` map below — slug →
home subject(s) — and scraped with the same renderer so the markdown +
index.json format stays identical.

Why an explicit map instead of frequency inference? A first pass tried to
guess each page's "home" subject from the most frequent course code. That
mislabeled English as THTR, Philosophy as CLAS, and General Engineering as
MECH, and let "Retail Studies Minor" through as a major. A wrong home subject
silently produces wrong ``required_courses`` and pollutes the R2
major-detection index. SCU subject codes are stable domain knowledge, so we
encode them once, here.

Usage (from project/course_planner/):
    python3 scripts/scrape_all_majors.py              # full run (writes files)
    python3 scripts/scrape_all_majors.py --dry-run    # list targets, no writes
    python3 scripts/scrape_all_majors.py --limit 3    # cap new majors (debug)

Writes (same targets as the curated scraper):
    data/majors/<major_id>.md
    data/majors/index.json
    data/major_requirements.json
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

from scripts.scrape_major_requirements import (  # noqa: E402
    POPULAR_MAJORS,
    _INDEX_PATH,
    _MAJORS_DIR,
    _write_legacy_json,
)
from utils.bulletin_major_scraper import (  # noqa: E402
    render_major_markdown,
    scrape_bulletin_major,
)

_BULLETIN_BASE = "https://www.scu.edu/bulletin/undergraduate/"

_CHAPTERS = {
    "arts_sciences": "chapter-3-college-of-arts-and-sciences",
    "business": "chapter-4-leavey-school-of-business",
    "engineering": "chapter-5-school-of-engineering",
}

# Authoritative slug → major spec(s) map. One bulletin page can host several
# majors (e.g. Modern Languages → French/Spanish/...); each spec gets its own
# home subject so the renderer extracts the right courses. Majors already in
# POPULAR_MAJORS (csen, math, csci, econ, biol, psyc, fnce, ...) are scraped
# from there and intentionally omitted here.
#
# spec keys: id, name, default_subject, subject_prefixes
_DISCOVERABLE_MAJORS: dict[str, dict[str, list[dict[str, Any]]]] = {
    "arts_sciences": {
        "anthropology": [
            {"id": "anth", "name": "Anthropology", "default_subject": "ANTH",
             "subject_prefixes": ["ANTH"]},
        ],
        "art-and-art-history": [
            {"id": "arth", "name": "Art History", "default_subject": "ARTH",
             "subject_prefixes": ["ARTH", "ARTS"]},
            {"id": "arts", "name": "Studio Art", "default_subject": "ARTS",
             "subject_prefixes": ["ARTS", "ARTH"]},
        ],
        "chemistry-and-biochemistry": [
            {"id": "chem", "name": "Chemistry", "default_subject": "CHEM",
             "subject_prefixes": ["CHEM", "MATH", "PHYS", "BIOL"]},
            {"id": "bioc", "name": "Biochemistry", "default_subject": "CHEM",
             "subject_prefixes": ["CHEM", "BIOL", "MATH", "PHYS"]},
        ],
        "child-studies": [
            {"id": "chst", "name": "Child Studies", "default_subject": "CHST",
             "subject_prefixes": ["CHST", "PSYC"]},
        ],
        "classics": [
            {"id": "clas", "name": "Classics", "default_subject": "CLAS",
             "subject_prefixes": ["CLAS", "HIST", "ARTH"]},
        ],
        "communication": [
            {"id": "comm", "name": "Communication", "default_subject": "COMM",
             "subject_prefixes": ["COMM"]},
        ],
        "english": [
            {"id": "engl", "name": "English", "default_subject": "ENGL",
             "subject_prefixes": ["ENGL"]},
        ],
        "environmental-studies-and-sciences": [
            {"id": "envs", "name": "Environmental Studies", "default_subject": "ENVS",
             "subject_prefixes": ["ENVS", "BIOL", "CENG", "POLI"]},
        ],
        "ethnic-studies": [
            {"id": "ethn", "name": "Ethnic Studies", "default_subject": "ETHN",
             "subject_prefixes": ["ETHN"]},
        ],
        "gender-and-sexuality-studies": [
            {"id": "gnsx", "name": "Gender and Sexuality Studies", "default_subject": "GNSX",
             "subject_prefixes": ["GNSX"]},
        ],
        "history": [
            {"id": "hist", "name": "History", "default_subject": "HIST",
             "subject_prefixes": ["HIST"]},
        ],
        # Modern Languages hosts THREE standalone majors (French, Italian,
        # Spanish). German/Chinese/Japanese are minors-only on this page, so
        # they are intentionally excluded. Each major is anchored to its own
        # "Major in <X>" heading so the renderer captures only that section.
        "modern-languages-and-literatures": [
            {"id": "fren", "name": "French and Francophone Studies", "default_subject": "FREN",
             "subject_prefixes": ["FREN"],
             "primary_bs_marker": "Major in French and Francophone Studies"},
            {"id": "ital", "name": "Italian Studies", "default_subject": "ITAL",
             "subject_prefixes": ["ITAL"],
             "primary_bs_marker": "Major in Italian Studies"},
            {"id": "span", "name": "Spanish Studies", "default_subject": "SPAN",
             "subject_prefixes": ["SPAN"],
             "primary_bs_marker": "Major in Spanish Studies"},
        ],
        "music": [
            {"id": "musc", "name": "Music", "default_subject": "MUSC",
             "subject_prefixes": ["MUSC"]},
        ],
        "neuroscience": [
            {"id": "neur", "name": "Neuroscience", "default_subject": "NEUR",
             "subject_prefixes": ["NEUR", "BIOL", "PSYC", "CHEM"]},
        ],
        "philosophy": [
            {"id": "phil", "name": "Philosophy", "default_subject": "PHIL",
             "subject_prefixes": ["PHIL"]},
        ],
        "physics-and-engineering-physics": [
            {"id": "phys", "name": "Physics", "default_subject": "PHYS",
             "subject_prefixes": ["PHYS", "MATH", "MECH"]},
        ],
        "political-science": [
            {"id": "poli", "name": "Political Science", "default_subject": "POLI",
             "subject_prefixes": ["POLI"]},
        ],
        "public-health-sciences": [
            {"id": "phsc", "name": "Public Health Science", "default_subject": "PHSC",
             "subject_prefixes": ["PHSC", "BIOL", "PSYC"]},
        ],
        "religious-studies": [
            {"id": "rsoc", "name": "Religious Studies", "default_subject": "RSOC",
             "subject_prefixes": ["RSOC", "SCTR", "TESP"]},
        ],
        "sociology": [
            {"id": "soci", "name": "Sociology", "default_subject": "SOCI",
             "subject_prefixes": ["SOCI"]},
        ],
        "theatre-and-dance": [
            {"id": "thtr", "name": "Theatre Arts", "default_subject": "THTR",
             "subject_prefixes": ["THTR", "DANC"]},
            {"id": "danc", "name": "Dance", "default_subject": "DANC",
             "subject_prefixes": ["DANC", "THTR"]},
        ],
    },
    "business": {
        # Most Leavey majors are curated. Entrepreneurship / International
        # Business / Retail Studies / Sustainable Food Systems are
        # emphases or minors, not standalone majors → intentionally omitted.
    },
    "engineering": {
        "general-engineering": [
            {"id": "genr", "name": "General Engineering", "default_subject": "ENGR",
             "subject_prefixes": ["ENGR", "MECH", "CENG", "ECEN", "MATH", "PHYS"]},
        ],
    },
}


def _detect_patterns(name: str) -> list[str]:
    low = name.lower().strip()
    pats = [low]
    if "major" not in low:
        pats.append(f"{low} major")
        pats.append(f"major in {low}")
    return pats


def _build_targets() -> list[dict[str, Any]]:
    """Flatten the authoritative map into scraper-ready meta dicts."""
    targets: list[dict[str, Any]] = []
    used_ids = set(POPULAR_MAJORS.keys())
    for school, chapter in _CHAPTERS.items():
        for slug, specs in _DISCOVERABLE_MAJORS.get(school, {}).items():
            url = f"{_BULLETIN_BASE}{chapter}/{slug}.html"
            for spec in specs:
                mid = spec["id"]
                if mid in used_ids:
                    print(f"  skip (id clash with curated): {mid}", file=sys.stderr)
                    continue
                used_ids.add(mid)
                targets.append(
                    {
                        "id": mid,
                        "name": spec["name"],
                        "url": url,
                        "school": school,
                        "default_subject": spec["default_subject"],
                        "subject_prefixes": spec["subject_prefixes"],
                        "detect_patterns": _detect_patterns(spec["name"]),
                        "primary_bs_marker": spec.get("primary_bs_marker"),
                        "tracks": spec.get("tracks"),
                        "senior_design_sequence": [],
                        "senior_design_final_year_only": False,
                    }
                )
    return targets


def _scrape_one(meta: dict[str, Any]) -> dict[str, Any] | None:
    """Scrape one major → write markdown, return its index.json entry."""
    major_id = meta["id"]
    try:
        scraped = scrape_bulletin_major(meta)
    except Exception as exc:  # noqa: BLE001
        print(f"  FAILED scrape {major_id}: {exc}", file=sys.stderr)
        return None
    md = render_major_markdown(scraped)
    (_MAJORS_DIR / f"{major_id}.md").write_text(md, encoding="utf-8")

    all_required: list[str] = []
    for tr in scraped.tracks:
        all_required.extend(tr.required_courses)
    seen: set[str] = set()
    deduped: list[str] = []
    for c in all_required:
        if c not in seen:
            seen.add(c)
            deduped.append(c)
    print(f"  → {major_id}.md ({len(scraped.courses)} courses, {len(deduped)} required)")
    return {
        "major_id": major_id,
        "name": scraped.name,
        "school": scraped.school,
        "bulletin_url": scraped.bulletin_url,
        "markdown_path": f"majors/{major_id}.md",
        "detect_patterns": scraped.detect_patterns,
        "required_courses": deduped,
        "senior_design_sequence": scraped.senior_design_sequence,
        "senior_design_final_year_only": scraped.senior_design_final_year_only,
        "course_count": len(scraped.courses),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape ALL SCU Bulletin majors to Markdown")
    parser.add_argument("--dry-run", action="store_true", help="list targets; write nothing")
    parser.add_argument("--limit", type=int, default=0, help="cap new majors scraped (debug)")
    args = parser.parse_args()

    targets = _build_targets()
    if args.limit:
        targets = targets[: args.limit]

    print(f"Curated majors: {len(POPULAR_MAJORS)}   Discoverable new: {len(targets)}")
    for t in targets:
        print(f"  + {t['id']:6} {t['name'][:42]:42} [{t['school']}] home={t['default_subject']}")

    if args.dry_run:
        print("\n(dry run — no files written)")
        return

    _MAJORS_DIR.mkdir(parents=True, exist_ok=True)
    index_entries: list[dict[str, Any]] = []

    # 1. Curated majors first (authoritative, hand-tuned metadata).
    for major_id, meta in POPULAR_MAJORS.items():
        print(f"Scraping curated {major_id} …")
        entry = _scrape_one(meta)
        if entry:
            index_entries.append(entry)
        time.sleep(0.4)

    # 2. Map-driven additional majors.
    for meta in targets:
        print(f"Scraping {meta['id']} …")
        entry = _scrape_one(meta)
        if entry:
            index_entries.append(entry)
        time.sleep(0.4)

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


if __name__ == "__main__":
    main()
