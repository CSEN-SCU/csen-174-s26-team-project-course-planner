"""Major degree requirements and prerequisite graph for SCU planners.

Per-major bulletin data lives in ``data/majors/<major_id>.md`` (one file per major).
Manifest: ``data/majors/index.json``. Compact legacy index: ``data/major_requirements.json``.

Refresh: ``python3 scripts/scrape_major_requirements.py``
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from utils.scu_course_schedule_xlsx import planned_section_keys

_DATA_ROOT = Path(__file__).resolve().parent.parent / "data"
_MAJORS_DIR = _DATA_ROOT / "majors"
_INDEX_PATH = _MAJORS_DIR / "index.json"
_DATA_PATH = _DATA_ROOT / "major_requirements.json"

_MARKDOWN_MAX_CHARS = 10_000

_COURSE_CODE_RE = re.compile(r"\b([A-Z]{2,6})\s+(\d{1,3}[A-Z]?)\b", re.IGNORECASE)

_SENIOR_DESIGN_RE = re.compile(
    r"\b(?:CSEN|COEN|ECEN|ELEN|ENGR)\s*/?\s*(?:CSEN|COEN|ECEN)?\s*19[246]L?\b",
    re.IGNORECASE,
)

# Bulletin units for the design-project sequence (not standard 4-unit + lab pairs).
_SENIOR_DESIGN_UNITS: dict[str, int] = {
    "CSEN 194": 1,
    "COEN 194": 1,
    "CSEN 194L": 1,
    "COEN 194L": 1,
    "CSEN 195": 2,
    "COEN 195": 2,
    "CSEN 196": 2,
    "COEN 196": 2,
}
# 195 and 196 are single courses — no companion lab section (digit after 19x).
_SENIOR_DESIGN_NO_LAB_DIGITS = frozenset({5, 6})

# Upper-division CSEN courses that strongly indicate a senior CSEN student.
_CSEN_SENIOR_MARKERS = frozenset(
    {
        "CSEN 171", "CSEN 174", "CSEN 175", "CSEN 177", "CSEN 179",
        "COEN 171", "COEN 174", "COEN 175", "COEN 177", "COEN 179",
    }
)


_SEASON_RANK = {"Fall": 0, "Winter": 1, "Spring": 2, "Summer": 3}
_SEASON_NEXT = {"Fall": "Winter", "Winter": "Spring", "Spring": "Fall"}


def _parse_term(term: str) -> tuple[str, int] | None:
    parts = str(term).split()
    if len(parts) != 2:
        return None
    season = parts[0].capitalize()
    if season not in _SEASON_RANK:
        return None
    try:
        return season, int(parts[1])
    except ValueError:
        return None


def _term_key(term: str) -> tuple[int, int]:
    """Chronological key; Winter/Spring share the academic year of the prior Fall."""
    p = _parse_term(term)
    if not p:
        return (9999, 9)
    season, year = p
    acad_year = year if season == "Fall" else year - 1
    return (acad_year, _SEASON_RANK[season])


def _term_next(term: str) -> str:
    p = _parse_term(term)
    if not p:
        return term
    season, year = p
    if season == "Fall":  # Fall → Winter crosses the calendar year
        year += 1
    return f"{_SEASON_NEXT[season]} {year}"


def _term_prev(term: str) -> str:
    """Previous SCU quarter (inverse of :func:`_term_next`)."""
    p = _parse_term(term)
    if not p:
        return term
    season, year = p
    if season == "Fall":
        return f"Spring {year}"
    if season == "Winter":
        return f"Fall {year - 1}"
    # Spring → Winter (same calendar year)
    return f"Winter {year}"


def _normalize_code(code: str | None) -> str:
    return (code or "").strip().upper()


def _expand_aliases(code: str, alias_map: dict[str, list[str]]) -> set[str]:
    norm = _normalize_code(code)
    out = {norm}
    for alt in alias_map.get(norm, []):
        out.add(_normalize_code(alt))
    for subj, num in planned_section_keys(norm):
        out.add(f"{subj} {num}".upper())
    return out


@lru_cache(maxsize=1)
def load_major_catalog() -> dict[str, Any]:
    if not _DATA_PATH.is_file():
        return {"majors": {}, "prerequisites": {}, "course_aliases": {}}
    with _DATA_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def clear_major_catalog_cache() -> None:
    load_major_catalog.cache_clear()
    load_major_index.cache_clear()
    load_major_markdown.cache_clear()


@lru_cache(maxsize=1)
def load_major_index() -> dict[str, Any]:
    if _INDEX_PATH.is_file():
        with _INDEX_PATH.open(encoding="utf-8") as f:
            return json.load(f)
    return {"majors": []}


def _major_index_by_id() -> dict[str, dict[str, Any]]:
    entries = load_major_index().get("majors") or []
    return {
        e["major_id"]: e
        for e in entries
        if isinstance(e, dict) and e.get("major_id")
    }


@lru_cache(maxsize=32)
def load_major_markdown(major_id: str) -> str | None:
    """Full bulletin markdown for one major (``data/majors/<id>.md``)."""
    path = _MAJORS_DIR / f"{major_id}.md"
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def _markdown_body_without_frontmatter(text: str) -> str:
    if text.startswith("---"):
        end = text.find("---", 3)
        if end >= 0:
            return text[end + 3 :].lstrip()
    return text


def _extract_senior_design_sections(body: str, sd_codes: list[str]) -> str:
    """Per-course catalog blocks for SD codes + the trailing SD sequence note."""
    chunks: list[str] = []
    seen: set[str] = set()
    for code in sd_codes:
        if not code or code in seen:
            continue
        seen.add(code)
        pat = re.compile(
            rf"###\s+{re.escape(code)}\s+—[\s\S]*?(?=\n\s*---\s*\n|\n##\s|\Z)",
            re.IGNORECASE,
        )
        m = pat.search(body)
        if m:
            chunks.append(m.group(0).strip())
    sd_section = re.search(
        r"##\s+Senior Design[\s\S]*?(?=\n##\s|\Z)",
        body,
        re.IGNORECASE,
    )
    if sd_section:
        chunks.append(sd_section.group(0).strip())
    return "\n\n---\n\n".join(chunks).strip()


def load_major_markdown_excerpt(major_id: str, *, max_chars: int = _MARKDOWN_MAX_CHARS) -> str:
    """Trimmed bulletin text for LLM prompts (requirements + prerequisite catalog).

    Senior-Design catalog entries and the trailing ``## Senior Design sequence``
    note live at the bottom of long bulletins, so naive truncation drops them.
    They are pinned to the tail of the excerpt so the LLM always sees the
    final-year sequencing rule.
    """
    raw = load_major_markdown(major_id)
    if not raw:
        return ""
    body = _markdown_body_without_frontmatter(raw)

    spec = (load_major_catalog().get("majors") or {}).get(major_id) or {}
    sd_codes = [
        _normalize_code(str(c))
        for c in (spec.get("senior_design_sequence") or [])
    ]
    sd_codes = [c for c in sd_codes if c]

    if len(body) <= max_chars:
        return body.strip()

    cut = body[:max_chars]
    last_hr = cut.rfind("\n---\n")
    if last_hr > max_chars // 2:
        cut = cut[:last_hr]

    truncated = cut.strip() + "\n\n(… bulletin excerpt truncated …)\n"

    pinned = _extract_senior_design_sections(body, sd_codes) if sd_codes else ""
    if not pinned:
        return truncated

    missing_catalog = any(f"### {code} " not in cut for code in sd_codes)
    missing_rule = "## Senior Design" not in cut
    if not (missing_catalog or missing_rule):
        return truncated

    return (
        truncated
        + "\n--- Senior Design sections (always preserved) ---\n\n"
        + pinned
        + "\n"
    )


def _parse_prereq_codes_from_text(text: str) -> list[list[str]]:
    """Split prerequisite prose into AND-groups of OR-alternatives (course codes)."""
    if not text.strip():
        return []
    groups: list[list[str]] = []
    for segment in re.split(r"\s+and\s+", text, flags=re.IGNORECASE):
        alts: list[str] = []
        for part in re.split(r"\s+or\s+", segment, flags=re.IGNORECASE):
            for subj, num in _COURSE_CODE_RE.findall(part.upper()):
                alts.append(f"{subj} {num}")
        if alts:
            groups.append(alts)
    return groups


@lru_cache(maxsize=32)
def _prerequisites_from_markdown(major_id: str) -> dict[str, list[list[str]]]:
    """course code → AND-groups of OR prerequisite codes."""
    raw = load_major_markdown(major_id)
    if not raw:
        return {}
    body = _markdown_body_without_frontmatter(raw)
    out: dict[str, list[list[str]]] = {}
    for m in re.finditer(
        r"###\s+([A-Z]{2,6}\s+\d{1,3}[A-Z]?)\s+—[\s\S]*?\*\*Prerequisites:\*\*\s*(.+?)(?:\n\n|\*\*Corequisites)",
        body,
        re.IGNORECASE,
    ):
        code = _normalize_code(m.group(1))
        out[code] = _parse_prereq_codes_from_text(m.group(2))
    return out


def _markdown_prereqs_met(
    course_code: str,
    completed: set[str],
    major_id: str,
    alias_map: dict[str, list[str]],
) -> bool | None:
    """Return True/False from markdown prereqs, or None if course not in bulletin file."""
    groups = _prerequisites_from_markdown(major_id).get(_normalize_code(course_code))
    if groups is None:
        return None
    if not groups:
        return True

    def _has(c: str) -> bool:
        return bool(_expand_aliases(c, alias_map) & completed)

    return all(any(_has(c) for c in group) for group in groups)


def _major_specs_for_detection() -> list[tuple[str, dict[str, Any]]]:
    """(major_id, spec) from index.json, falling back to legacy catalog."""
    out: list[tuple[str, dict[str, Any]]] = []
    seen: set[str] = set()
    for entry in load_major_index().get("majors") or []:
        if not isinstance(entry, dict):
            continue
        mid = str(entry.get("major_id") or "").strip()
        if mid and mid not in seen:
            seen.add(mid)
            out.append((mid, entry))
    for mid, spec in (load_major_catalog().get("majors") or {}).items():
        if mid not in seen and isinstance(spec, dict):
            out.append((mid, spec))
    return out


def _haystack_from_progress(
    missing_details: list[dict[str, Any]] | None,
    parsed_rows: list[dict[str, Any]] | None,
) -> str:
    parts: list[str] = []
    for item in missing_details or []:
        if not isinstance(item, dict):
            continue
        for field in ("requirement", "category", "course"):
            val = item.get(field)
            if isinstance(val, str) and val.strip():
                parts.append(val)
    for row in parsed_rows or []:
        if not isinstance(row, dict):
            continue
        rq = row.get("requirement")
        if isinstance(rq, str) and rq.strip():
            parts.append(rq)
    return "\n".join(parts).lower()


def score_majors_from_progress(
    missing_details: list[dict[str, Any]] | None = None,
    parsed_rows: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Rank majors by how well Workday text matches bulletin detect_patterns."""
    haystack = _haystack_from_progress(missing_details, parsed_rows)
    if not haystack.strip():
        return []

    ranked: list[dict[str, Any]] = []
    for major_id, spec in _major_specs_for_detection():
        score = 0
        for pattern in spec.get("detect_patterns") or []:
            if isinstance(pattern, str) and pattern.lower() in haystack:
                score += 3
        prefix = major_id.upper()[:4]
        for item in missing_details or []:
            if not isinstance(item, dict):
                continue
            text = " ".join(
                str(item.get(k) or "")
                for k in ("requirement", "category", "course")
            ).upper()
            if prefix in text or (major_id == "csen" and ("CSEN" in text or "COEN" in text)):
                score += 1
        if score > 0:
            ranked.append(
                {
                    "major_id": major_id,
                    "name": spec.get("name") or major_id.upper(),
                    "score": score,
                }
            )
    ranked.sort(key=lambda x: (-int(x["score"]), str(x["major_id"])))
    return ranked


def detect_major_detailed(
    missing_details: list[dict[str, Any]] | None = None,
    parsed_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Infer major with confidence for UI confirmation.

    Returns:
        major_id, name, confidence (high|low|none), needs_confirmation, candidates
    """
    ranked = score_majors_from_progress(missing_details, parsed_rows)
    if not ranked:
        return {
            "major_id": None,
            "name": None,
            "confidence": "none",
            "needs_confirmation": True,
            "candidates": [],
            "message": (
                "We could not tell your major from the Academic Progress export. "
                "Please choose your major below."
            ),
        }

    top = ranked[0]
    score = int(top["score"])
    second_score = int(ranked[1]["score"]) if len(ranked) > 1 else 0

    if score >= 6 or (score >= 3 and score - second_score >= 2):
        confidence = "high"
    elif score >= 2:
        confidence = "low"
    else:
        confidence = "none"

    major_id = top["major_id"] if confidence != "none" else None
    name = top["name"] if major_id else None

    if confidence == "high":
        msg = f"We read your Academic Progress Report as: {name}. Confirm or change below."
    elif confidence == "low":
        msg = (
            f"Your progress file might be {name}, but we're not sure. "
            "Please confirm or pick another major."
        )
    else:
        msg = "Please select your major so we can apply the right degree requirements."

    return {
        "major_id": major_id,
        "name": name,
        "confidence": confidence,
        "needs_confirmation": True,
        "candidates": ranked[:5],
        "message": msg,
    }


def detect_major(
    missing_details: list[dict[str, Any]] | None = None,
    parsed_rows: list[dict[str, Any]] | None = None,
) -> str | None:
    """Infer major id (e.g. ``csen``) from Workday requirement text."""
    detailed = detect_major_detailed(missing_details, parsed_rows)
    if detailed.get("confidence") == "none":
        return None
    return detailed.get("major_id")


# SCU treats Computer Science & Engineering as one major; Workday/transcripts
# may label it "coen" while the bulletin catalog is keyed "csen". Normalize so
# catalog lookups (senior design, bulletin requirements) don't silently miss.
_MAJOR_ID_ALIASES = {"coen": "csen"}


def normalize_major_id(major_id: str | None) -> str | None:
    if not major_id:
        return major_id
    mid = str(major_id).strip().lower()
    return _MAJOR_ID_ALIASES.get(mid, mid)


def resolve_major_id(
    *,
    confirmed_major_id: str | None = None,
    missing_details: list[dict[str, Any]] | None = None,
    parsed_rows: list[dict[str, Any]] | None = None,
) -> str | None:
    """User-confirmed major wins; otherwise infer from progress."""
    if confirmed_major_id and str(confirmed_major_id).strip():
        return normalize_major_id(str(confirmed_major_id))
    return normalize_major_id(detect_major(missing_details, parsed_rows))


def major_display_name(major_id: str | None) -> str | None:
    if not major_id:
        return None
    mid = major_id.strip().lower()
    for entry in load_major_index().get("majors") or []:
        if isinstance(entry, dict) and entry.get("major_id") == mid:
            return str(entry.get("name") or mid)
    spec = (load_major_catalog().get("majors") or {}).get(mid)
    if isinstance(spec, dict):
        return str(spec.get("name") or mid)
    return mid.upper()


def _codes_from_missing(missing_details: list[dict[str, Any]] | None) -> set[str]:
    codes: set[str] = set()
    for item in missing_details or []:
        if not isinstance(item, dict):
            continue
        explicit = _normalize_code(item.get("course"))
        if explicit:
            codes.add(explicit)
        for field in ("requirement", "category"):
            val = item.get(field)
            if not isinstance(val, str):
                continue
            for m in _COURSE_CODE_RE.finditer(val.upper()):
                codes.add(f"{m.group(1)} {m.group(2)}")
    return codes


# Intro programming (CSEN/COEN 10) is superseded when the student already
# completed the next courses in the track (e.g. COEN 11 → CSEN 12).
_INTRO_PROGRAMMING_RE = re.compile(
    r"\b(?:CSEN|COEN)\s*/?\s*(?:CSEN|COEN)?\s*10\b",
    re.IGNORECASE,
)
_INTRO_PROGRAMMING_CODES = frozenset(
    {"CSEN 10", "COEN 10", "CSEN 10L", "COEN 10L"},
)
_INTRO_SUPERSEDING_COMPLETED = frozenset(
    {
        "COEN 11", "COEN 11L", "CSEN 11", "CSEN 11L",
        "CSEN 12", "CSEN 12L", "CSEN 19", "CSEN 20", "CSEN 20L",
        "CSEN 79", "CSEN 79L",
    },
)


def _requirement_is_intro_programming(req: str, codes: set[str]) -> bool:
    if _INTRO_PROGRAMMING_RE.search(req):
        return True
    if not codes:
        return False
    return codes <= _INTRO_PROGRAMMING_CODES


def _completed_supersedes_intro(completed: set[str], alias_map: dict[str, list[str]]) -> bool:
    for marker in _INTRO_SUPERSEDING_COMPLETED:
        if _expand_aliases(marker, alias_map) & completed:
            return True
    return False


@lru_cache(maxsize=32)
def _prerequisite_dependents(major_id: str) -> dict[str, list[str]]:
    """Map prerequisite code → bulletin courses that list it."""
    deps: dict[str, list[str]] = {}
    for course, groups in _prerequisites_from_markdown(major_id).items():
        for group in groups:
            for prereq in group:
                key = _normalize_code(prereq)
                deps.setdefault(key, [])
                if course not in deps[key]:
                    deps[key].append(course)
    return deps


def filter_superseded_missing_details(
    missing_details: list[dict[str, Any]] | None,
    completed: set[str],
    *,
    major_id: str | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Drop Workday gaps the student has clearly already passed in practice.

    Returns ``(kept, notes)`` where ``notes`` are short advisor messages for
    the plan ``advice`` field (Workday may still show the requirement open).
    """
    if not missing_details:
        return [], []

    mid = normalize_major_id(major_id)
    catalog = load_major_catalog()
    alias_map = catalog.get("course_aliases") or {}
    deps = _prerequisite_dependents(mid) if mid else {}

    kept: list[dict[str, Any]] = []
    notes: list[str] = []

    for item in missing_details:
        if not isinstance(item, dict):
            continue
        req = str(item.get("requirement") or item.get("category") or "").strip()
        codes = set()
        explicit = _normalize_code(item.get("course"))
        if explicit:
            codes.add(explicit)
        for m in _COURSE_CODE_RE.finditer(req.upper()):
            codes.add(f"{m.group(1)} {m.group(2)}")

        if _requirement_is_intro_programming(req, codes) and _completed_supersedes_intro(
            completed, alias_map
        ):
            notes.append(
                f"{req}: not scheduled — you already completed later programming "
                f"courses (e.g. COEN 11 / CSEN 12). Workday may still list "
                f"CSEN/COEN 10 as open; resolve with your advisor if needed."
            )
            continue

        superseded = False
        for code in codes:
            for dependent in deps.get(code, []):
                if _expand_aliases(dependent, alias_map) & completed:
                    notes.append(
                        f"{req}: not scheduled — {dependent} is already completed, "
                        f"so {code} is treated as satisfied for planning."
                    )
                    superseded = True
                    break
            if superseded:
                break
        if superseded:
            continue

        kept.append(item)

    return kept, notes


def _prereq_rule_satisfied(
    rule: dict[str, Any],
    completed: set[str],
    alias_map: dict[str, list[str]],
) -> bool:
    def _has(code: str) -> bool:
        return bool(_expand_aliases(code, alias_map) & completed)

    for code in rule.get("requires") or []:
        if not _has(str(code)):
            return False

    # Each inner list is an OR-group; every group must have at least one hit.
    for group in rule.get("requires_any") or []:
        if not isinstance(group, list):
            continue
        if not any(_has(str(c)) for c in group):
            return False

    for code in rule.get("also_requires") or []:
        if not _has(str(code)):
            return False

    for group in rule.get("also_requires_any") or []:
        if not isinstance(group, list):
            continue
        if not any(_has(str(c)) for c in group):
            return False

    return True


def prerequisites_met(
    course_code: str,
    completed: set[str],
    *,
    catalog: dict[str, Any] | None = None,
    major_id: str | None = None,
) -> bool:
    cat = catalog or load_major_catalog()
    alias_map = cat.get("course_aliases") or {}
    norm = _normalize_code(course_code)

    if major_id:
        md_result = _markdown_prereqs_met(norm, completed, major_id, alias_map)
        if md_result is not None:
            return md_result

    prereqs = cat.get("prerequisites") or {}
    rule = prereqs.get(norm)
    if not rule:
        return True
    return _prereq_rule_satisfied(rule, completed, alias_map)


def unmet_prerequisites(
    course_code: str,
    completed: set[str],
    *,
    catalog: dict[str, Any] | None = None,
) -> list[str]:
    """Human-readable list of prerequisite courses still needed."""
    cat = catalog or load_major_catalog()
    prereqs = cat.get("prerequisites") or {}
    alias_map = cat.get("course_aliases") or {}
    rule = prereqs.get(_normalize_code(course_code))
    if not rule:
        return []

    missing: list[str] = []

    def _has(code: str) -> bool:
        return bool(_expand_aliases(code, alias_map) & completed)

    for code in rule.get("requires") or []:
        c = str(code)
        if not _has(c):
            missing.append(c)

    for group in rule.get("requires_any") or []:
        if isinstance(group, list) and not any(_has(str(c)) for c in group):
            missing.append(" OR ".join(str(c) for c in group))

    for code in rule.get("also_requires") or []:
        c = str(code)
        if not _has(c):
            missing.append(c)

    for group in rule.get("also_requires_any") or []:
        if isinstance(group, list) and not any(_has(str(c)) for c in group):
            missing.append(" OR ".join(str(c) for c in group))

    return missing


def remaining_major_courses(
    major_id: str,
    completed: set[str],
    missing_details: list[dict[str, Any]] | None = None,
) -> list[str]:
    """Required major courses not yet completed (catalog minus transcript)."""
    catalog = load_major_catalog()
    spec = (catalog.get("majors") or {}).get(major_id)
    if not spec:
        return []

    alias_map = catalog.get("course_aliases") or {}
    gap_codes = _codes_from_missing(missing_details)

    pool: list[str] = list(spec.get("required_courses") or [])
    pool.extend(spec.get("senior_design_sequence") or [])
    seen_pool: set[str] = set()
    remaining: list[str] = []
    for raw in pool:
        code = _normalize_code(str(raw))
        if not code or code in seen_pool:
            continue
        seen_pool.add(code)
        if _expand_aliases(code, alias_map) & completed:
            continue
        remaining.append(code)
    return remaining


def infer_academic_stage(
    major_id: str | None,
    completed: set[str],
) -> str:
    """Rough year label: freshman | sophomore | junior | senior | unknown."""
    if not major_id:
        return "unknown"
    if major_id == "csen":
        if _expand_aliases("CSEN 174", load_major_catalog().get("course_aliases") or {}) & completed:
            return "senior"
        if _CSEN_SENIOR_MARKERS & completed:
            return "senior"
        if _expand_aliases("CSEN 122", load_major_catalog().get("course_aliases") or {}) & completed:
            return "junior"
        if _expand_aliases("CSEN 20", load_major_catalog().get("course_aliases") or {}) & completed:
            return "sophomore"
        if _expand_aliases("CSEN 11", load_major_catalog().get("course_aliases") or {}) & completed:
            return "sophomore"
        return "freshman"
    return "unknown"


def _senior_design_codes(major_id: str) -> list[str]:
    catalog = load_major_catalog()
    spec = (catalog.get("majors") or {}).get(major_id) or {}
    seq = spec.get("senior_design_sequence") or []
    out: list[str] = []
    for code in seq:
        c = _normalize_code(str(code))
        if c and c not in out:
            out.append(c)
        if c.endswith("L"):
            continue
        lab = c + "L" if not c.endswith("L") else c
        if lab not in out:
            out.append(lab)
    return out


def next_senior_design_course(
    major_id: str,
    completed: set[str],
) -> str | None:
    """Next course in 192→194→195→196 chain the student still needs."""
    catalog = load_major_catalog()
    alias_map = catalog.get("course_aliases") or {}
    lectures = [
        c
        for c in _senior_design_codes(major_id)
        if not c.endswith("L") and c != "CSEN 192"
    ]
    # Optional intro — skip if student already finished a later SD course.
    later_done = any(
        _expand_aliases(c, alias_map) & completed for c in lectures if c != "CSEN 192"
    )
    for base in lectures:
        if base == "CSEN 192" and later_done:
            continue
        if _expand_aliases(base, alias_map) & completed:
            continue
        return base
    return None


def build_major_advisor_block(
    *,
    missing_details: list[dict[str, Any]] | None,
    parsed_rows: list[dict[str, Any]] | None = None,
    completed: set[str] | None = None,
    confirmed_major_id: str | None = None,
) -> tuple[str, str | None]:
    """Prompt section + resolved major id."""
    major_id = resolve_major_id(
        confirmed_major_id=confirmed_major_id,
        missing_details=missing_details,
        parsed_rows=parsed_rows,
    )
    if not major_id:
        return "", None

    catalog = load_major_catalog()
    spec = (catalog.get("majors") or {}).get(major_id) or {}
    name = major_display_name(major_id) or spec.get("name") or major_id.upper()
    source = "student-confirmed" if confirmed_major_id else "inferred from Academic Progress"
    completed_set = completed or set()

    stage = infer_academic_stage(major_id, completed_set)
    remaining = remaining_major_courses(major_id, completed_set, missing_details)

    ready: list[str] = []
    blocked: list[tuple[str, list[str]]] = []
    for code in remaining:
        if prerequisites_met(code, completed_set, catalog=catalog, major_id=major_id):
            ready.append(code)
        else:
            unmet = unmet_prerequisites(code, completed_set, catalog=catalog)
            if unmet:
                blocked.append((code, unmet))

    lines = [
        "=== STUDENT MAJOR (from degree requirements catalog) ===",
        f"Major: {name} ({major_id}) — {source}",
        f"Inferred academic stage: {stage}",
    ]

    sd_next = next_senior_design_course(major_id, completed_set)
    if sd_next and spec.get("senior_design_final_year_only"):
        lines.append(
            f"Senior Design: engineering majors take CSEN/COEN 194 → 195 → 196 "
            f"one per quarter in the FINAL year. Next in sequence for this student: {sd_next} "
            f"(+ lab section in the same quarter)."
        )
        if stage == "senior":
            lines.append(
                "PRIORITY: This student appears to be a senior — if Senior Design or "
                f"{sd_next} is offered next term, include it unless the student explicitly "
                "asks for a lighter load or defers it."
            )

    if ready:
        lines.append(
            "Major courses ready to take (prerequisites satisfied): "
            + ", ".join(ready[:12])
            + (" …" if len(ready) > 12 else "")
        )
    if blocked:
        lines.append("Blocked until prerequisites are met:")
        for code, unmet in blocked[:10]:
            lines.append(f"  • {code} needs: {', '.join(unmet)}")
        if len(blocked) > 10:
            lines.append(f"  … and {len(blocked) - 10} more")

    gap_has_sd = any(
        isinstance(item, dict)
        and any(
            isinstance(item.get(f), str) and _SENIOR_DESIGN_RE.search(item[f])
            for f in ("requirement", "category", "course")
        )
        for item in (missing_details or [])
    )
    if gap_has_sd:
        lines.append(
            "Workday still lists Senior Design (194/195/196) as unsatisfied — "
            "do NOT skip the sequence in favor of only Core/GE fillers."
        )

    excerpt = load_major_markdown_excerpt(major_id)
    if excerpt:
        lines.append("")
        lines.append(
            "=== MAJOR BULLETIN (requirements & per-course prerequisites) ==="
        )
        lines.append(f"File: data/majors/{major_id}.md")
        lines.append(excerpt)

    lines.append("")
    return "\n".join(lines) + "\n", major_id


def enforce_senior_design_in_final_quarters(
    plan: dict[str, Any],
    major_id: str | None,
    *,
    completed: set[str] | None = None,
) -> dict[str, Any]:
    """Move 194/195/196 (+ labs) into the last three plan quarters when possible."""
    major_id = normalize_major_id(major_id)
    if not major_id:
        return plan
    catalog = load_major_catalog()
    spec = (catalog.get("majors") or {}).get(major_id) or {}
    if not spec.get("senior_design_final_year_only"):
        return plan

    sd_bases = [
        c for c in _senior_design_codes(major_id)
        if not c.endswith("L") and c not in ("CSEN 192",)
    ]
    if not sd_bases:
        return plan

    quarters = plan.get("quarters") or []
    if not isinstance(quarters, list) or not quarters:
        return plan

    alias_map = catalog.get("course_aliases") or {}
    _ = completed  # accepted for API compatibility; placement is term-driven

    def _is_sd_course(course_code: str) -> bool:
        norm = _normalize_code(course_code)
        base = norm[:-1] if norm.endswith("L") else norm
        for sd in sd_bases:
            if norm == sd or norm == sd + "L":
                return True
            if base in _expand_aliases(sd, alias_map):
                return True
        return False

    # Pull every senior-design entry out of wherever the model put it; we
    # re-place them deterministically below.
    sd_entries: list[dict[str, Any]] = []
    for q in quarters:
        if not isinstance(q, dict):
            continue
        kept: list[dict[str, Any]] = []
        for c in q.get("courses") or []:
            if isinstance(c, dict) and _is_sd_course(str(c.get("course") or "")):
                sd_entries.append(c)
            else:
                kept.append(c)
        q["courses"] = kept
        q["total_units"] = sum(int(x.get("units") or 0) for x in kept if isinstance(x, dict))

    if not sd_entries:
        return plan

    # Group each course (lecture + its lab) by the 194/195/196 number so they
    # stay together and map to the correct quarter of the senior year.
    groups: dict[int, list[dict[str, Any]]] = {}
    for entry in sd_entries:
        code = _normalize_code(str(entry.get("course") or ""))
        base = code[:-1] if code.endswith("L") else code
        m = re.search(r"19(\d)", base)
        digit = int(m.group(1)) if m else 9
        groups.setdefault(digit, []).append(entry)
    for entries in groups.values():
        entries.sort(key=lambda e: 1 if _normalize_code(str(e.get("course") or "")).endswith("L") else 0)

    # Senior design is a locked Fall→Winter→Spring sequence: 194 in Fall, 195
    # in the following Winter, 196 in the following Spring of the SAME academic
    # (senior) year. Anchor it to a Spring term at the END of the plan so the
    # final three quarters are exactly Fall, Winter, Spring.
    existing_terms = [
        str(q.get("term") or "")
        for q in quarters
        if isinstance(q, dict) and (q.get("courses") or [])
    ]
    last_term = (
        max(existing_terms, key=_term_key)
        if existing_terms
        else str(plan.get("graduation_term") or "")
    )
    spring = last_term
    guard = 0
    while _parse_term(spring) and _parse_term(spring)[0] != "Spring" and guard < 12:
        spring = _term_next(spring)
        guard += 1
    winter = _term_prev(spring)
    fall = _term_prev(winter)
    sd_terms = {4: fall, 5: winter, 6: spring}

    qmap = {str(q.get("term") or ""): q for q in quarters if isinstance(q, dict)}

    def _get_or_create(term: str) -> dict[str, Any]:
        q = qmap.get(term)
        if q is None:
            q = {"term": term, "courses": [], "total_units": 0}
            qmap[term] = q
            quarters.append(q)
        return q

    for digit in sorted(groups):
        term = sd_terms.get(digit, spring)
        q = _get_or_create(term)
        placed: list[dict[str, Any]] = []
        for entry in groups[digit]:
            code = _normalize_code(str(entry.get("course") or ""))
            if digit in _SENIOR_DESIGN_NO_LAB_DIGITS and code.endswith("L"):
                continue
            if code in _SENIOR_DESIGN_UNITS:
                entry = dict(entry)
                entry["units"] = _SENIOR_DESIGN_UNITS[code]
            placed.append(entry)
        q["courses"] = list(q.get("courses") or []) + placed
        q["total_units"] = sum(int(x.get("units") or 0) for x in q["courses"] if isinstance(x, dict))

    # Drop quarters left empty after the move and re-sort chronologically.
    quarters = [
        q for q in quarters if isinstance(q, dict) and (q.get("courses") or [])
    ]
    quarters.sort(key=lambda q: _term_key(str(q.get("term") or "")))
    plan["quarters"] = quarters
    if quarters:
        plan["graduation_term"] = str(quarters[-1].get("term") or "")
    return normalize_senior_design_courses(plan, major_id)


def normalize_senior_design_courses(
    plan: dict[str, Any],
    major_id: str | None,
) -> dict[str, Any]:
    """Apply correct units and drop spurious 195L/196L lab rows."""
    major_id = normalize_major_id(major_id)
    if not major_id:
        return plan
    catalog = load_major_catalog()
    spec = (catalog.get("majors") or {}).get(major_id) or {}
    if not spec.get("senior_design_final_year_only"):
        return plan

    sd_bases = [
        c for c in _senior_design_codes(major_id)
        if not c.endswith("L") and c not in ("CSEN 192",)
    ]

    def _sd_digit(code: str) -> int | None:
        m = re.search(r"19(\d)", _normalize_code(code))
        return int(m.group(1)) if m else None

    def _is_sd(code: str) -> bool:
        norm = _normalize_code(code)
        for sd in sd_bases:
            if norm == sd or norm == sd + "L":
                return True
        return False

    for q in plan.get("quarters") or []:
        if not isinstance(q, dict):
            continue
        kept: list[dict[str, Any]] = []
        for c in q.get("courses") or []:
            if not isinstance(c, dict):
                continue
            code = _normalize_code(str(c.get("course") or ""))
            if not _is_sd(code):
                kept.append(c)
                continue
            digit = _sd_digit(code)
            if digit in _SENIOR_DESIGN_NO_LAB_DIGITS and code.endswith("L"):
                continue
            row = dict(c)
            if code in _SENIOR_DESIGN_UNITS:
                row["units"] = _SENIOR_DESIGN_UNITS[code]
            kept.append(row)
        q["courses"] = kept
        q["total_units"] = sum(int(x.get("units") or 0) for x in kept)
    return plan
