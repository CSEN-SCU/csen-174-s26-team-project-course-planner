from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional


_COURSE_CODE_RE = re.compile(r"^[A-Z]{2,6}\s+\d{1,4}[A-Z]{0,2}\b", re.IGNORECASE)
_QUARTER_HEADER_RE = re.compile(
    r"^\s*(?P<season>Fall|Winter|Spring|Summer)\s+(?P<year>\d{4})\s+Quarter\b",
    re.IGNORECASE,
)
# Example: "ECON 1 ECON 1 - Principles of Microeconomics 4.000 CR"
_EXTERNAL_LINE_RE = re.compile(
    r"""
    ^\s*
    (?P<code>[A-Z]{2,6}\s+\d{1,4}[A-Z]{0,2})\s+
    (?P<title>.+?)\s+
    (?P<units>\d+\.\d{3})\s+
    (?P<grade>[A-Z]{1,2}[+-]?|CR|P|NP|W)\s*$
    """,
    re.IGNORECASE | re.VERBOSE,
)

def _norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip())


def _norm_code(code: str) -> str:
    return _norm_ws(code).upper()


@dataclass
class _CourseBuilder:
    code: str
    term: Optional[str] = None
    title_parts: list[str] = field(default_factory=list)
    numbers: list[str] = field(default_factory=list)
    tail_tokens: list[str] = field(default_factory=list)

    def feed_title_continuation(self, line: str) -> None:
        t = _norm_ws(line)
        if t:
            self.title_parts.append(t)

    def finalize(self) -> Optional[dict[str, Any]]:
        """
        Convert buffered course row into a structured record.
        Expected tail pattern (common Workday unofficial):
          Attempted Earned Grade Points
          4.000 4.000 B 0.000
        """
        if len(self.numbers) < 3:
            return None

        attempted = self.numbers[0]
        earned = self.numbers[1]
        points = self.numbers[-1]

        # grade token is between earned and points
        mid_tokens = self.tail_tokens[:]
        if not mid_tokens:
            return None

        grade_raw = mid_tokens[0]
        grade_norm = _norm_ws(grade_raw)
        if grade_norm.lower() == "in progress":
            grade_norm = "In Progress"

        title = _norm_ws(" ".join(self.title_parts)) if self.title_parts else None

        # Units: prefer Attempted as "units" for planning purposes
        units_f: Optional[float] = None
        try:
            units_f = float(attempted)
        except ValueError:
            units_f = None

        return {
            "code": _norm_code(self.code),
            "title": title,
            "term": self.term,
            "grade": grade_norm,
            "units": units_f,
            "attempted_units": float(attempted) if re.fullmatch(r"\d+\.\d+", attempted) else None,
            "earned_units": float(earned) if re.fullmatch(r"\d+\.\d+", earned) else None,
            "points": float(points) if re.fullmatch(r"\d+\.\d+", points) else None,
        }


def _is_noise_line(line: str) -> bool:
    s = line.strip()
    if not s:
        return True
    if s.startswith("Santa Clara University"):
        return True
    if "Student Name:" in s or "Student ID:" in s or "Date of Birth:" in s:
        return True
    if s.startswith("Page ") and "/ " in s:
        return True
    if s.startswith("Course Transcript Course Title"):
        return True
    if s.startswith("Course Description Earned Grade"):
        return True
    if s.startswith("Attempted Earned Grade"):
        return True
    if s.startswith("Term GPA") or s.startswith("Cum GPA"):
        return True
    if s.startswith("Total Transfer Credit"):
        return True
    if s.endswith("Academic Programs") or s.endswith("Major") or "Pathway" in s:
        # keep conservative: only drop obvious header-ish lines
        if "Major" in s and "Programs" in s:
            return True
    return False


def _parse_external_block_line(line: str, term: Optional[str]) -> Optional[dict[str, Any]]:
    m = _EXTERNAL_LINE_RE.match(line.strip())
    if not m:
        return None
    code = _norm_code(m.group("code"))
    title = _norm_ws(m.group("title"))
    title = re.sub(rf"^{re.escape(code)}\s*-\s*", "", title, flags=re.IGNORECASE).strip()
    units = float(m.group("units"))
    grade = m.group("grade").upper()
    return {"code": code, "title": title, "term": term, "grade": grade, "units": units}


def parse_scu_workday_unofficial_transcript(text: str) -> list[dict[str, Any]]:
    """
    Deterministic parser for SCU Workday unofficial transcript text dumps.

    This is intentionally conservative: it focuses on the repeated table rows:
      CODE  TITLE...  attempted earned grade points
    and supports multi-line titles between CODE and the numeric tail.
    """
    lines = [ln.rstrip("\n") for ln in text.splitlines()]

    current_term: Optional[str] = None
    in_external_test_credit = False

    active: Optional[_CourseBuilder] = None
    out: dict[str, dict[str, Any]] = {}

    def flush_active() -> None:
        nonlocal active
        if not active:
            return
        rec = active.finalize()
        active = None
        if not rec:
            return
        code = rec["code"]
        # Prefer the richest record if duplicates appear
        prev = out.get(code)
        if prev is None:
            out[code] = rec
            return

        def richness(d: dict[str, Any]) -> int:
            score = 0
            for k in ("title", "term", "grade", "units", "attempted_units", "earned_units", "points"):
                if d.get(k) is not None:
                    score += 1
            return score

        out[code] = rec if richness(rec) >= richness(prev) else prev

    for raw in lines:
        line = raw.strip()
        if not line:
            # Blank lines are common inside a course title block; do NOT flush an in-progress row.
            if not active:
                continue
            continue

        qh = _QUARTER_HEADER_RE.match(line)
        if qh:
            flush_active()
            current_term = f"{qh.group('season').title()} {qh.group('year')}"
            in_external_test_credit = False
            continue

        if "External Test Credit" in line:
            flush_active()
            in_external_test_credit = True
            continue

        if in_external_test_credit:
            # External Test Credit formatting varies a lot in PDF pastes.
            # For prototype reliability, only ingest obvious single-line rows and skip the rest.
            if _is_noise_line(line):
                continue
            rec = _parse_external_block_line(line, term=None)
            if rec:
                out.setdefault(rec["code"], rec)
            continue

        if _is_noise_line(line):
            # don't flush on noise; noise can appear between title continuation lines
            continue

        # Start of a course row: begins with DEPT + NUMBER
        if _COURSE_CODE_RE.match(line):
            flush_active()

            # Split code + remainder
            m = re.match(
                r"^\s*(?P<code>[A-Z]{2,6}\s+\d{1,4}[A-Z]{0,2})\s+(?P<rest>.+)\s*$",
                line,
                flags=re.IGNORECASE,
            )
            if not m:
                continue
            code = _norm_code(m.group("code"))
            rest = m.group("rest").strip()

            active = _CourseBuilder(code=code, term=current_term)

            # If remainder already contains numeric tail, parse in-line
            # Pattern: TITLE ... 4.000 4.000 B 0.000
            num_tail = re.search(r"(\d+\.\d{3})\s+(\d+\.\d{3})\s+(.+?)\s+(\d+\.\d{3})\s*$", rest)
            if num_tail:
                title_part = rest[: num_tail.start()].strip()
                if title_part:
                    active.title_parts.append(title_part)
                active.numbers = [num_tail.group(1), num_tail.group(2), num_tail.group(4)]
                tail = num_tail.group(3).strip()
                # tail may be "B" or "In Progress" (possibly multi-word)
                # Normalize multi-word grades
                active.tail_tokens = [tail]
            else:
                # Title begins; continuation lines follow until numeric tail line
                if rest:
                    active.title_parts.append(rest)
            continue

        # Continuation / numeric tail for active course
        if active:
            # Numeric tail line
            mnums = re.fullmatch(
                r"(?P<a>\d+\.\d{3})\s+(?P<e>\d+\.\d{3})\s+(?P<g>.+?)\s+(?P<p>\d+\.\d{3})",
                line.strip(),
            )
            if mnums:
                active.numbers = [mnums.group("a"), mnums.group("e"), mnums.group("p")]
                g = mnums.group("g").strip()
                if g.lower() == "in progress":
                    g = "In Progress"
                active.tail_tokens = [g]
                flush_active()
                continue

            # Title continuation (avoid swallowing footer-ish lines)
            if line.startswith("Attempted") or line.startswith("Term GPA"):
                flush_active()
                continue

            active.feed_title_continuation(line)
            continue

        # No active builder: ignore

    flush_active()
    return list(out.values())


def merge_by_code(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}

    def richness(d: dict[str, Any]) -> int:
        score = 0
        for k in ("title", "term", "grade", "units", "attempted_units", "earned_units", "points"):
            v = d.get(k)
            if v is not None and v != "":
                score += 1
        return score

    for rec in records:
        if not isinstance(rec, dict):
            continue
        code = rec.get("code")
        if not isinstance(code, str):
            continue
        code_n = _norm_code(code)
        rec2 = {**rec, "code": code_n}
        prev = best.get(code_n)
        if prev is None or richness(rec2) > richness(prev):
            best[code_n] = rec2
    return list(best.values())
