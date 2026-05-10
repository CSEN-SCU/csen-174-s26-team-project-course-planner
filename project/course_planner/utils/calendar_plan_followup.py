"""Natural-language follow-ups when the student removes a course from the weekly preview.

Used as ``user_preference`` for ``plan_for_user(..., previous_plan=...)`` so the
planning agent treats it as a follow-up against CURRENT STATE.
"""

from __future__ import annotations

from typing import Any, Optional


def build_remove_and_replace_preference(
    courses: list[str],
    day_column_label: Optional[str],
    parsed: Optional[dict[str, Any]],
) -> str:
    """Ask the model to drop ``courses`` and suggest gap-based replacement(s) for the vacated slot."""
    cleaned = [" ".join(str(c).split()).strip() for c in (courses or []) if str(c).strip()]
    codes = cleaned or ["(unknown course)"]
    codes_fmt = ", ".join(f"**{c}**" for c in codes)
    codes_plain = ", ".join(codes)
    if parsed and day_column_label:
        slot_desc = f"{day_column_label} {parsed['start']} – {parsed['end']}"
    elif parsed:
        days = ", ".join(str(d) for d in (parsed.get("days") or []) if d)
        slot_desc = f"{days} {parsed['start']} – {parsed['end']}"
    else:
        slot_desc = "Time TBD (no meeting pattern matched in Find Course Sections)"

    primary_removed = codes[0]
    return (
        f"Remove {codes_fmt} from the plan. Your `recommended` array must NOT include any of these codes: "
        f"{codes_plain}. "
        f"The removed course(s) are included again in STUDENT REQUIREMENTS (missing_details) as unfinished gap(s). "
        f"suggest ONE replacement course for the freed time slot: {slot_desc}. "
        f"The replacement must be from missing_details and must have a section available in that time slot "
        f"in SCU_Find_Course_Sections.xlsx. "
        f"If the replacement lecture has a lab co-requisite in missing_details (same quarter, catalog number + "
        f"trailing L), recommend the lecture and lab together as a pair in `recommended`. "
        f"In `assistant_reply`, state `removed: {primary_removed}` (and partner code if applicable), the "
        f"replacement course code(s), and which requirement category from missing_details they satisfy. "
        f"If no gap course can fit that slot in the workbook, say so briefly."
    )
