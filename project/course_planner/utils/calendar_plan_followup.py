"""Natural-language follow-ups when the student removes a course from the weekly preview.

Used as ``user_preference`` for ``plan_for_user(..., previous_plan=...)`` so the
planning agent treats it as a follow-up against CURRENT STATE.
"""

from __future__ import annotations

from typing import Any, Optional


def build_remove_and_replace_preference(
    course: str,
    day_column_label: Optional[str],
    parsed: Optional[dict[str, Any]],
) -> str:
    """Ask the model to drop ``course`` and add a gap-based replacement for the vacated slot."""
    code = " ".join(str(course or "").split()).strip() or "(unknown course)"
    if parsed and day_column_label:
        slot = (
            f"The vacated weekly slot is **{day_column_label}** "
            f"{parsed['start']} – {parsed['end']} (same wall-clock window as the removed course)."
        )
    elif parsed:
        days = ", ".join(str(d) for d in (parsed.get("days") or []) if d)
        slot = (
            f"Target meeting window from the removed course: **{days}** "
            f"{parsed['start']} – {parsed['end']}."
        )
    else:
        slot = (
            "Meeting time for this course was unknown (**Time TBD**); choose a replacement from "
            "remaining gaps that fits the student's overall preferences and avoids obvious conflicts."
        )

    return (
        f"Remove **{code}** from the plan. Your `recommended` array must NOT include **{code}**. "
        f"Add one replacement course taken from the student's unfinished requirements in "
        f"STUDENT REQUIREMENTS (missing_details). "
        f"{slot} "
        f"In `assistant_reply`, state `removed: {code}`, the replacement course code, and which "
        f"**category / requirement label** from missing_details the replacement satisfies. "
        f"If no gap course can honor that time window, say so briefly and still propose the best alternative."
    )
