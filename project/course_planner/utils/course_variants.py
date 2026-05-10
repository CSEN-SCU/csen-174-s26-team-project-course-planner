"""Course code variant expansion (shared by schedule map and slot verification)."""

from __future__ import annotations

import re

from utils.scu_course_schedule_xlsx import expand_subjects_for_schedule_lookup


def extract_course_variants(course_str: str) -> list[str]:
    """
    Input: "CSEN/COEN 194/L", "COEN 146", "ECEN/ELEN 153 & 153L", or "ENGL103"
    Output: all plausible course-code variants
    Example: ["CSEN 194", "COEN 194", "CSEN 194L", "COEN 194L"]
    """
    s = " ".join((course_str or "").split())
    if not s:
        return []
    if " " not in s and "/" not in s and "&" not in s:
        m = re.fullmatch(r"([A-Za-z]{2,8})(\d+[A-Za-z]?)", s, re.I)
        if m:
            s = f"{m.group(1).upper()} {m.group(2).upper()}"
    parts = s.split()
    subjects = expand_subjects_for_schedule_lookup(parts[0].split("/"))
    rest = " ".join(parts[1:])
    numbers = []
    for token in re.split(r"[/&,]", rest):
        token = token.strip()
        if token:
            if token.isalpha() and numbers:
                numbers.append(numbers[-1] + token)
            else:
                numbers.append(token)
    variants = []
    for subj in subjects:
        for num in numbers:
            variants.append(f"{subj} {num}".strip())
    return variants
