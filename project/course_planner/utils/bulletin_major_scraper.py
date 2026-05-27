"""Parse SCU Undergraduate Bulletin major pages → per-major Markdown."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from html import unescape
from typing import Any
from urllib.request import Request, urlopen

_COURSE_IN_TEXT = re.compile(r"\b([A-Z]{2,6})\s+(\d{1,3}[A-Z]?)\b")
_COURSE_H3 = re.compile(
    r"<h3>\s*<span[^>]*>\s*(\d{1,3}[A-Z]?)\.\s*([^<]+?)\s*</span>\s*</h3>",
    re.IGNORECASE,
)
_PREREQ_IN_P = re.compile(
    r"Prerequisites?:\s*([^.<]+(?:\.[^.<]*)?)",
    re.IGNORECASE,
)
_COREQ_IN_P = re.compile(
    r"Corequisites?:\s*([^.<]+(?:\.[^.<]*)?)",
    re.IGNORECASE,
)
_UNITS_IN_P = re.compile(r"\((\d+)\s*units?\)", re.IGNORECASE)


@dataclass
class CourseEntry:
    code: str
    title: str
    units: str | None = None
    prerequisites: str | None = None
    corequisites: str | None = None
    description: str | None = None


@dataclass
class MajorTrack:
    name: str
    required_courses: list[str] = field(default_factory=list)
    raw_bullets: list[str] = field(default_factory=list)


@dataclass
class ScrapedMajor:
    major_id: str
    name: str
    school: str
    bulletin_url: str
    detect_patterns: list[str]
    senior_design_sequence: list[str]
    senior_design_final_year_only: bool
    tracks: list[MajorTrack]
    courses: list[CourseEntry]
    subject_prefixes: list[str]


def fetch_bulletin_html(url: str) -> str:
    req = Request(url, headers={"User-Agent": "SCU-Course-Planner/1.0 (academic project)"})
    with urlopen(req, timeout=90) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _tag_text(html_fragment: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", html_fragment, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _extract_paragraph_after(h3_end: int, html: str, max_len: int = 4000) -> str:
    chunk = html[h3_end : h3_end + max_len]
    m = re.search(r"<p[^>]*>([\s\S]*?)</p>", chunk, re.I)
    if not m:
        return ""
    return _tag_text(m.group(1))


def _codes_from_bullet_html(fragment: str, allowed_prefixes: set[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for m in _COURSE_IN_TEXT.finditer(fragment.upper()):
        subj, num = m.group(1), m.group(2)
        if subj not in allowed_prefixes:
            continue
        if not num[0].isdigit():
            continue
        code = f"{subj} {num}"
        if code not in seen:
            seen.add(code)
            ordered.append(code)
    return ordered


def _extract_tracks(
    html: str,
    track_markers: list[dict[str, str]] | None,
    *,
    allowed_prefixes: set[str],
    primary_bs_marker: str | None = None,
) -> list[MajorTrack]:
    plain = _tag_text(html)
    tracks: list[MajorTrack] = []

    if track_markers:
        for tm in track_markers:
            marker = tm["marker"]
            idx = plain.find(marker)
            if idx < 0:
                continue
            end = len(plain)
            for other in track_markers:
                if other["marker"] == marker:
                    continue
                j = plain.find(other["marker"], idx + len(marker))
                if j > idx:
                    end = min(end, j)
            for stop in (
                "Requirements for the Minor",
                "Minor in ",
                "Lower-Division Courses",
                "Courses:",
            ):
                j = plain.find(stop, idx + len(marker))
                if j > idx:
                    end = min(end, j)
            section = plain[idx:end]
            tracks.append(
                MajorTrack(
                    name=tm["name"],
                    required_courses=_codes_from_bullet_html(section, allowed_prefixes),
                    raw_bullets=[],
                )
            )
        if tracks:
            return tracks

    # Single-track: anchor on this major's B.S. title when provided.
    start = 0
    name = "Degree requirements"
    if primary_bs_marker:
        idx = plain.find(primary_bs_marker)
        if idx >= 0:
            start = idx
            name = primary_bs_marker.strip()
    else:
        for m in (
            "Requirements for the Majors",
            "Requirements for the Major",
            "departmental requirements",
        ):
            idx = plain.find(m)
            if idx >= 0:
                start = max(start, idx)

    end = len(plain)
    for stop in (
        "Bachelor of Science in Web",
        "Bachelor of Science in General",
        "Requirements for the Minor",
        "Minor in ",
        "Lower-Division Courses",
        "Upper-Division Courses",
        "Courses:",
    ):
        j = plain.find(stop, start + 40)
        if j > start:
            end = min(end, j)

    section = plain[start:end]
    return [
        MajorTrack(
            name=name,
            required_courses=_codes_from_bullet_html(section, allowed_prefixes),
            raw_bullets=[],
        )
    ]


def _parse_department_courses(
    html: str,
    default_subject: str,
    subject_prefixes: list[str],
) -> list[CourseEntry]:
    prefixes = {p.upper() for p in subject_prefixes}
    prefixes.add(default_subject.upper())
    courses: list[CourseEntry] = []
    seen: set[str] = set()

    for m in _COURSE_H3.finditer(html):
        num, title = m.group(1).upper(), _tag_text(m.group(2))
        body = _extract_paragraph_after(m.end(), html)
        if not body:
            continue
        # Skip cross-department h3 that are not this major's subject (e.g. ENGL on CS page)
        subj = default_subject.upper()
        code = f"{subj} {num}"
        if code in seen:
            continue
        seen.add(code)

        prereq_m = _PREREQ_IN_P.search(body)
        coreq_m = _COREQ_IN_P.search(body)
        units_m = _UNITS_IN_P.search(body)
        desc = body
        if prereq_m:
            desc = _PREREQ_IN_P.split(desc, maxsplit=1)[0].strip()

        courses.append(
            CourseEntry(
                code=code,
                title=title,
                units=units_m.group(1) if units_m else None,
                prerequisites=_tag_text(prereq_m.group(1)) if prereq_m else None,
                corequisites=_tag_text(coreq_m.group(1)) if coreq_m else None,
                description=desc[:500] if desc else None,
            )
        )

    # Also pick up courses explicitly prefixed in descriptions (ECEN page uses CSEN in lists)
    for m in _COURSE_IN_TEXT.finditer(_tag_text(html).upper()):
        subj, num = m.group(1), m.group(2)
        if subj not in prefixes:
            continue
        code = f"{subj} {num}"
        if code in seen:
            continue
        # Only add if we have a nearby prereq line in HTML for that code
        pat = rf"{subj}\s*{num}[^<]{{0,40}}Prerequisite"
        if not re.search(pat, html, re.I):
            continue
        seen.add(code)
        courses.append(CourseEntry(code=code, title="(see bulletin)", prerequisites=None))

    def _sort_key(c: CourseEntry) -> tuple[str, int, int]:
        m = re.search(r"(\d+)", c.code)
        num = int(m.group(1)) if m else 0
        return (c.code.split()[0], num, 1 if c.code.endswith("L") else 0)

    courses.sort(key=_sort_key)
    return courses


def scrape_bulletin_major(meta: dict[str, Any]) -> ScrapedMajor:
    major_id = meta["id"]
    html = fetch_bulletin_html(meta["url"])
    default_subject = meta.get("default_subject") or major_id.upper()[:4]
    subject_prefixes = list(meta.get("subject_prefixes") or [default_subject])
    allowed = {p.upper() for p in subject_prefixes}
    tracks = _extract_tracks(
        html,
        meta.get("tracks"),
        allowed_prefixes=allowed,
        primary_bs_marker=meta.get("primary_bs_marker"),
    )
    courses = _parse_department_courses(html, default_subject, subject_prefixes)

    return ScrapedMajor(
        major_id=major_id,
        name=meta["name"],
        school=meta.get("school", ""),
        bulletin_url=meta["url"],
        detect_patterns=list(meta.get("detect_patterns") or []),
        senior_design_sequence=list(meta.get("senior_design_sequence") or []),
        senior_design_final_year_only=bool(meta.get("senior_design_final_year_only")),
        tracks=tracks,
        courses=courses,
        subject_prefixes=subject_prefixes,
    )


def render_major_markdown(scraped: ScrapedMajor) -> str:
    today = date.today().isoformat()
    lines = [
        "---",
        f"major_id: {scraped.major_id}",
        f"name: {scraped.name}",
        f"school: {scraped.school}",
        f"bulletin_url: {scraped.bulletin_url}",
        f"scraped_at: {today}",
        "detect_patterns:",
    ]
    for p in scraped.detect_patterns:
        lines.append(f"  - {p}")
    if scraped.senior_design_sequence:
        lines.append("senior_design_sequence:")
        for c in scraped.senior_design_sequence:
            lines.append(f"  - {c}")
    lines.append(
        f"senior_design_final_year_only: {str(scraped.senior_design_final_year_only).lower()}"
    )
    # Flatten required courses for agents / JSON index
    all_required: list[str] = []
    for tr in scraped.tracks:
        all_required.extend(tr.required_courses)
    seen: set[str] = set()
    deduped: list[str] = []
    for c in all_required:
        if c not in seen:
            seen.add(c)
            deduped.append(c)
    lines.append("required_courses:")
    for c in deduped:
        lines.append(f"  - {c}")
    lines.extend(["---", ""])
    lines.append(f"# {scraped.name}")
    lines.append("")
    lines.append(f"Source: [SCU Undergraduate Bulletin]({scraped.bulletin_url})")
    lines.append(f"Scraped: {today}")
    lines.append("")

    for tr in scraped.tracks:
        lines.append(f"## {tr.name}")
        lines.append("")
        if tr.required_courses:
            lines.append("### Required courses (from bulletin)")
            lines.append("")
            for code in tr.required_courses:
                lines.append(f"- {code}")
            lines.append("")

    lines.append("## Course prerequisites (department catalog)")
    lines.append("")
    lines.append(
        "Each section lists official bulletin prerequisites/corequisites. "
        "The planner agent should not recommend a course until prerequisites are satisfied."
    )
    lines.append("")

    for entry in scraped.courses:
        lines.append(f"### {entry.code} — {entry.title}")
        lines.append("")
        if entry.units:
            lines.append(f"Units: {entry.units}")
            lines.append("")
        if entry.prerequisites:
            lines.append(f"**Prerequisites:** {entry.prerequisites}")
            lines.append("")
        if entry.corequisites:
            lines.append(f"**Corequisites:** {entry.corequisites}")
            lines.append("")
        if entry.description:
            lines.append(entry.description)
            lines.append("")
        lines.append("---")
        lines.append("")

    if scraped.senior_design_sequence:
        lines.append("## Senior Design sequence (engineering)")
        lines.append("")
        seq = " → ".join(scraped.senior_design_sequence)
        lines.append(
            f"Schedule **one course per quarter in the final year**, in order: {seq}. "
            "Always pair lecture with trailing-L lab in the same quarter."
        )
        lines.append("")

    return "\n".join(lines)
