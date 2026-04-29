from __future__ import annotations

import json
import re
from typing import Any, Literal, Optional

import httpx

from .config import (
    AI_PROVIDER,
    GEMINI_API_BASE_URL,
    GEMINI_API_KEY,
    GEMINI_MODEL,
)

from .scu_workday_parse import merge_by_code, parse_scu_workday_unofficial_transcript

ProviderName = Literal["gemini", "none"]


def effective_provider() -> ProviderName:
    p = AI_PROVIDER
    if p in {"none", "off", "disabled"}:
        return "none"
    if p == "gemini":
        return "gemini" if bool(GEMINI_API_KEY) else "none"

    # auto
    if GEMINI_API_KEY:
        return "gemini"
    return "none"


def ai_enabled() -> bool:
    return effective_provider() != "none"


def ai_provider_label() -> str:
    p = effective_provider()
    if p == "gemini":
        return "Gemini"
    return "未启用"


def _extract_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    # Strip common ```json fences
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, flags=re.DOTALL | re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    return json.loads(text)


async def gemini_json_chat(system: str, user: str) -> dict[str, Any]:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set")

    url = f"{GEMINI_API_BASE_URL}/v1beta/models/{GEMINI_MODEL}:generateContent"
    params = {"key": GEMINI_API_KEY}
    base_generation = {"temperature": 0.2, "responseMimeType": "application/json"}

    async with httpx.AsyncClient(timeout=60) as client:
        payload = {
            "generationConfig": base_generation,
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
        }
        resp = await client.post(url, params=params, json=payload)
        if resp.status_code == 400:
            # Some models/endpoints may not accept systemInstruction; fall back to a single user turn.
            combined = f"{system}\n\nUSER INPUT:\n{user}"
            payload = {
                "generationConfig": base_generation,
                "contents": [{"role": "user", "parts": [{"text": combined}]}],
            }
            resp = await client.post(url, params=params, json=payload)
        resp.raise_for_status()
        data = resp.json()

    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        raise ValueError(f"Unexpected Gemini response shape: {data}") from e

    return _extract_json_object(text)


async def json_chat(system: str, user: str) -> dict[str, Any]:
    provider = effective_provider()
    if provider == "gemini":
        return await gemini_json_chat(system, user)
    raise RuntimeError("No AI provider configured (set GEMINI_API_KEY, or AI_PROVIDER=none)")


_COURSE_RE = re.compile(r"\b([A-Z]{2,6})\s+(\d{1,4}[A-Z]{0,2})\b", re.IGNORECASE)
_SEASON_WORDS = {
    "SPRING",
    "SUMMER",
    "FALL",
    "AUTUMN",
    "WINTER",
    "QTR",
    "QUARTER",
    "SEMESTER",
}
_MONTH_FULL_NAMES = {
    "JANUARY",
    "FEBRUARY",
    "MARCH",
    "APRIL",
    "MAY",
    "JUNE",
    "JULY",
    "AUGUST",
    "SEPTEMBER",
    "OCTOBER",
    "NOVEMBER",
    "DECEMBER",
}
_MONTH_ABBREVS = {
    "JAN",
    "FEB",
    "MAR",
    "APR",
    "MAY",
    "JUN",
    "JUL",
    "AUG",
    "SEP",
    "SEPT",
    "OCT",
    "NOV",
    "DEC",
}

_NON_COURSE_DEPTS = {
    # Common transcript summary/noise tokens that match DEPT+NUMBER but aren't courses
    "CREDIT",
    "CREDITS",
    "TRANSFER",
    "TOTAL",
    "TOTALS",
    "TERM",
    "GPA",
}
_TERM_HEADER_RE = re.compile(
    r"^\s*(SPRING|SUMMER|FALL|AUTUMN|WINTER)\s+(\d{4})\s*$",
    re.IGNORECASE,
)
_LINE_COURSE_RE = re.compile(
    r"""
    ^\s*
    (?P<code>(?P<dept>[A-Z]{2,6})\s+(?P<num>\d{1,4}[A-Z]{0,2}))
    \b
    (?P<rest>.*)$
    """,
    re.IGNORECASE | re.VERBOSE,
)


def _normalize_course_code(code: str) -> str:
    c = code.strip().upper()
    c = re.sub(r"\s+", " ", c)
    return c


def looks_like_real_course_code(code: str) -> bool:
    """
    Filter obvious non-courses like 'SPRING 2026' that can match generic DEPT+NUMBER regex.
    """
    c = _normalize_course_code(code)
    m = re.fullmatch(r"([A-Z]{2,6})\s+(\d{1,4}[A-Z]{0,2})", c)
    if not m:
        return False

    dept, num = m.group(1), m.group(2)
    if dept in _SEASON_WORDS:
        return False
    if dept in _NON_COURSE_DEPTS:
        return False
    # Full month names are never subject codes in this context (e.g. APRIL 20).
    if dept in _MONTH_FULL_NAMES:
        return False

    # Reject YEAR-shaped "numbers" when paired with season-like dept (extra safety)
    if dept in {"SPRING", "SUMMER", "FALL", "AUTUMN", "WINTER"}:
        return False

    # If numeric part is a calendar year, it's almost never a course number in this context
    if re.fullmatch(r"\d{4}", num):
        y = int(num)
        if 1900 <= y <= 2100:
            return False

    # 3-letter month abbrevs can look like subject codes (e.g. MAR). Only treat NARROW
    # day-shaped tails (1-2 digits, 1-31) as header noise; allow MAR 101-style catalog numbers.
    if dept in _MONTH_ABBREVS and re.fullmatch(r"\d{1,2}", num):
        day = int(num)
        if 1 <= day <= 31:
            return False

    return True


def _best_effort_parse_line(line: str) -> Optional[dict[str, Any]]:
    m = _LINE_COURSE_RE.match(line)
    if not m:
        return None
    code = _normalize_course_code(m.group("code"))
    if not looks_like_real_course_code(code):
        return None

    rest = m.group("rest") or ""
    rest = rest.strip()

    title = None
    grade = None
    units = None

    # Strip common separators after the course code
    rest = re.sub(r"^[-–—:：|]+\s*", "", rest).strip()

    # Common patterns:
    # - "CSEN 177 - Data Structures  4.00  A"
    # - "CSEN 177 Data Structures 4.00 A"
    # - "CSEN 177L Lab Section"
    tail = rest
    t_m = re.search(r"[-–—:：]\s*(.+)$", rest)
    if t_m:
        tail = t_m.group(1).strip()

    tokens = [x for x in re.split(r"\s+", tail) if x]
    if tokens:
        last = tokens[-1]
        if re.fullmatch(r"[ABCDF][+-]?|P|NP|W|CR|NC|IN|IP", last, flags=re.IGNORECASE):
            grade = last.upper()
            tokens = tokens[:-1]

        # Units in parentheses, e.g. "Something (4) B+"
        if tokens and re.fullmatch(r"\(\d+(?:\.\d+)?\)", tokens[-1]):
            inner = tokens[-1][1:-1]
            try:
                units = float(inner)
            except ValueError:
                units = None
            tokens = tokens[:-1]

        if tokens and re.fullmatch(r"\d+(\.\d+)?", tokens[-1]):
            try:
                units = float(tokens[-1])
            except ValueError:
                units = None
            tokens = tokens[:-1]
        if tokens:
            title = " ".join(tokens).strip()

    return {
        "code": code,
        "title": title,
        "term": None,
        "grade": grade,
        "units": units,
    }


def line_parse_transcript(text: str) -> list[dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    current_term: Optional[str] = None
    pending_code: Optional[str] = None

    term_anywhere_re = re.compile(r"\b(FALL|WINTER|SPRING|SUMMER|AUTUMN)\s+(\d{4})\b", re.IGNORECASE)
    header_noise_re = re.compile(
        r"^\s*(COURSE|TRANSCRIPT|TITLE|ATTEMPTED|EARNED|GRADE|POINTS|TERM\s+GPA|CUMULATIVE|TOTAL)\b",
        re.IGNORECASE,
    )

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            pending_code = None
            continue

        # Track terms even when embedded in longer headers like "Fall 2023 Quarter (...)"
        t_any = term_anywhere_re.search(line)
        if t_any:
            current_term = f"{t_any.group(1).title()} {t_any.group(2)}"
            pending_code = None
            continue

        if _TERM_HEADER_RE.match(line):
            current_term = line.strip().title()
            pending_code = None
            continue

        # If previous line was only a course code, treat this line as possible title continuation.
        if pending_code and not _LINE_COURSE_RE.match(line) and not header_noise_re.match(line):
            prev = out.get(pending_code)
            if prev and not prev.get("title"):
                prev["title"] = line
                if current_term and not prev.get("term"):
                    prev["term"] = current_term
            pending_code = None
            continue

        rec = _best_effort_parse_line(line)
        if not rec:
            pending_code = None
            continue
        code = rec["code"]
        if current_term:
            rec["term"] = current_term
        out.setdefault(code, rec)

        # If the line is basically just the code (or produced no title), allow next line to fill title.
        if not rec.get("title"):
            pending_code = code
        else:
            pending_code = None
    return list(out.values())


def sanitize_ai_courses(courses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []
    for c in courses:
        if not isinstance(c, dict):
            continue
        code = c.get("code")
        if not isinstance(code, str):
            continue
        code_n = _normalize_course_code(code)
        if not looks_like_real_course_code(code_n):
            continue

        def opt_str(k: str) -> Any:
            v = c.get(k)
            return v if isinstance(v, str) else None

        title = opt_str("title")
        term = opt_str("term")
        grade = opt_str("grade")

        units = c.get("units")
        units_f = None
        if isinstance(units, (int, float)):
            units_f = float(units)
        elif isinstance(units, str):
            try:
                units_f = float(units.strip())
            except ValueError:
                units_f = None

        def opt_float(k: str) -> Optional[float]:
            v = c.get(k)
            if isinstance(v, (int, float)):
                return float(v)
            if isinstance(v, str):
                try:
                    return float(v.strip())
                except ValueError:
                    return None
            return None

        cleaned.append(
            {
                "code": code_n,
                "title": title,
                "term": term,
                "grade": grade,
                "units": units_f,
                "attempted_units": opt_float("attempted_units"),
                "earned_units": opt_float("earned_units"),
                "points": opt_float("points"),
            }
        )
    return cleaned


def merge_course_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Merge multiple extractors keyed by normalized course code, preferring richer records.
    """

    def score(rec: dict[str, Any]) -> int:
        s = 0
        for k in ("title", "term", "grade", "units", "attempted_units", "earned_units", "points"):
            if rec.get(k) is not None:
                s += 1
        return s

    best: dict[str, dict[str, Any]] = {}
    for rec in records:
        if not isinstance(rec, dict):
            continue
        code = rec.get("code")
        if not isinstance(code, str):
            continue
        code_n = _normalize_course_code(code)
        if not looks_like_real_course_code(code_n):
            continue
        rec2 = {**rec, "code": code_n}
        prev = best.get(code_n)
        if prev is None or score(rec2) > score(prev):
            best[code_n] = rec2
    return list(best.values())


def heuristic_parse_transcript(text: str) -> list[dict[str, Any]]:
    """
    Very small fallback parser for demo reliability.
    """
    hits: dict[str, dict[str, Any]] = {}
    for m in _COURSE_RE.finditer(text.upper()):
        dept, num = m.group(1), m.group(2)
        code = _normalize_course_code(f"{dept} {num}")
        if not looks_like_real_course_code(code):
            continue
        hits.setdefault(code, {"code": code})
    return list(hits.values())


async def parse_transcript_with_ai(transcript_text: str) -> list[dict[str, Any]]:
    system = (
        "You extract structured course records from a college transcript (often SCU Workday unofficial transcript) "
        "or a course list. Your job is to reliably extract the COURSE NAME (title) along with term/grade/units when present.\n\n"
        "Return STRICT JSON ONLY in this shape:\n"
        "{"
        "\"courses\":["
        "{"
        "\"code\":\"COEN 12\","
        "\"title\":null,"
        "\"term\":null,"
        "\"grade\":null,"
        "\"units\":null,"
        "\"attempted_units\":null,"
        "\"earned_units\":null,"
        "\"points\":null"
        "}"
        "]"
        "}\n\n"
        "Extraction rules (critical):\n"
        "- A valid course code MUST match: 2-6 letters, space, then a catalog number like 12 / 177 / 177L / 12A (letters only as suffix).\n"
        "- NEVER output dates or transcript metadata as courses (examples to IGNORE: 'APRIL 20', 'JUNE 01', 'Prepared On', 'Date of Birth').\n"
        "- NEVER output summary/noise rows as courses (examples to IGNORE: 'CREDIT 4', 'TOTAL 12', 'TERM GPA', 'CUMULATIVE').\n"
        "- NEVER output term headers like 'SPRING 2026', 'FALL 2025', 'WINTER 2027' as a course code.\n"
        "- Titles may appear on the SAME line as the course code OR on the NEXT line (course code alone on a line then title). Capture it.\n"
        "- Terms may appear as headers like 'Fall 2023 Quarter (...)'. Apply that term to subsequent courses until the next term header.\n"
        "- For Workday tables, units/grade/points may appear as separate columns; parse them when present.\n"
        "- If unsure about any field, use null. Do NOT invent.\n"
    )
    user = transcript_text.strip()

    # Gemini-first: if AI is available, trust AI extraction for names/terms, then use deterministic
    # parsers only as fallback/merge to fill gaps.
    ai_clean: list[dict[str, Any]] = []
    try:
        data = await json_chat(system, user)
        courses = data.get("courses")
        if isinstance(courses, list):
            ai_clean = sanitize_ai_courses([c for c in courses if isinstance(c, dict)])
    except Exception:
        ai_clean = []

    scu = parse_scu_workday_unofficial_transcript(transcript_text)
    line = line_parse_transcript(transcript_text)
    heur = heuristic_parse_transcript(transcript_text)

    if ai_clean:
        # Prefer AI; merge in other extractors only to fill missing fields.
        return merge_by_code([*ai_clean, *scu, *line, *heur])

    # AI unavailable/failed: fall back to deterministic parsing
    return merge_by_code([*scu, *line, *heur])


async def enrich_rationales_with_ai(payload: dict[str, Any]) -> dict[str, Any]:
    system = (
        "You write short, honest rationales for course recommendations for SCU undergrad planning. "
        "Return STRICT JSON: {\"items\":[{\"code\":\"COEN 21\",\"bullets\":[\"...\",\"...\"],\"risks\":[\"...\"]}]} "
        "Do not invent facts not supported by the input JSON. If data is missing, say so explicitly."
    )
    user = json.dumps(payload, ensure_ascii=False)
    data = await json_chat(system, user)
    items = data.get("items")
    if not isinstance(items, list):
        raise ValueError("Invalid AI JSON: missing items[]")
    return data
