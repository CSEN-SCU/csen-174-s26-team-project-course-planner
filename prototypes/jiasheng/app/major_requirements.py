from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import httpx
from bs4 import BeautifulSoup


_CODE_RE = re.compile(r"\b([A-Z]{2,6})\s*(\d{1,4}[A-Z]{0,2})\b")


@dataclass(frozen=True)
class MajorRequirements:
    source_url: str
    sections: dict[str, list[str]]
    option_groups: list[list[str]]
    notes: list[str]


def _norm_code(dept: str, num: str) -> str:
    return f"{dept.upper()} {num.upper()}"


async def fetch_major_requirements(url: str, timeout_s: float = 20.0) -> MajorRequirements:
    async with httpx.AsyncClient(
        timeout=timeout_s,
        headers={
            "User-Agent": "SCU Course Planner Prototype (educational) / httpx",
            "Accept": "text/html,application/xhtml+xml",
        },
        follow_redirects=True,
    ) as client:
        r = await client.get(url)
        r.raise_for_status()
        html = r.text

    soup = BeautifulSoup(html, "html.parser")

    # Prefer main content, but fall back to whole document.
    root = soup.find("main") or soup

    # Heuristic: requirements pages tend to use headings and then bullet lists.
    headings = root.find_all(["h2", "h3", "h4", "h5"])

    sections: dict[str, list[str]] = {}
    option_groups: list[list[str]] = []
    notes: list[str] = []

    def add_code(section: str, code: str) -> None:
        cur = sections.setdefault(section, [])
        # preserve page order (stable)
        if code not in cur:
            cur.append(code)

    # Walk heading blocks and capture course codes in the immediately-following lists (ul/ol)
    # until the next heading. Avoid parsing free-form paragraphs because they often contain
    # substitutions/notes (e.g. "approved substitutions for CHEM 11 are ...") that should not
    # be treated as required courses.
    for h in headings:
        title = h.get_text(" ", strip=True)
        if not title:
            continue
        # Keep only headings that look like requirement categories.
        if len(title) < 3:
            continue

        # Normalize a small set of headings: strip extra whitespace
        section_name = re.sub(r"\s+", " ", title).strip()

        node = h
        collected_any = False
        for _ in range(0, 60):  # hard cap
            node = node.find_next_sibling()
            if node is None:
                break
            if node.name in {"h2", "h3", "h4", "h5"}:
                break

            if node.name in {"ul", "ol"}:
                for li in node.find_all("li", recursive=True):
                    txt = li.get_text(" ", strip=True)
                    if not txt:
                        continue
                    # Detect "one of the following" option blocks and record their choices.
                    txt_l = txt.lower()
                    nested = li.find(["ul", "ol"])
                    if nested and ("one of the following" in txt_l or "one of these" in txt_l):
                        group: list[str] = []
                        for opt_li in nested.find_all("li", recursive=True):
                            opt_txt = opt_li.get_text(" ", strip=True)
                            if not opt_txt:
                                continue
                            for m in _CODE_RE.finditer(opt_txt.upper()):
                                dept, num = m.group(1), m.group(2)
                                code = _norm_code(dept, num)
                                if code not in group:
                                    group.append(code)
                        if group:
                            option_groups.append(group)
                        # Don't treat option codes as required codes here.
                        continue
                    for m in _CODE_RE.finditer(txt.upper()):
                        dept, num = m.group(1), m.group(2)
                        add_code(section_name, _norm_code(dept, num))
                        collected_any = True
                continue

            # Keep small notes (not used as codes) for UI inspection/debugging
            if node.name in {"p", "div"}:
                txt = node.get_text(" ", strip=True)
                if txt and any(x in txt.lower() for x in ("unit", "elective", "must", "substitution")):
                    notes.append(f"{section_name}: {txt[:240]}")

        if not collected_any:
            continue

    # If parsing produced too little, do a whole-page fallback bucket.
    if sum(len(v) for v in sections.values()) < 10:
        page_text = root.get_text("\n", strip=True).upper()
        codes = {_norm_code(m.group(1), m.group(2)) for m in _CODE_RE.finditer(page_text)}
        if codes:
            sections.setdefault("All (fallback)", []).extend(sorted(codes))

    # De-dup within each section while preserving order
    for k, vals in list(sections.items()):
        seen: set[str] = set()
        deduped: list[str] = []
        for v in vals:
            if v in seen:
                continue
            seen.add(v)
            deduped.append(v)
        sections[k] = deduped

    return MajorRequirements(source_url=url, sections=sections, option_groups=option_groups, notes=notes[:50])

