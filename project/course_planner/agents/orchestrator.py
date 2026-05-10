"""Per-user planning orchestrator: retrieve -> plan -> write-back.

`plan_for_user(user_id, missing_details, user_preference)` is the single
entrypoint main.py calls. It:

1. Retrieves up to ``MEMORY_TOP_K`` per-user memory snippets relevant to
   the current preference + gap query.
2. Calls ``run_planning_agent`` with those snippets injected into the
   prompt prefix (the planning agent enforces a char budget so the
   prompt never balloons).
3. After a successful plan, writes a compact summary back to memory so
   future quarters benefit from the running context.

The professor enrichment step stays in main.py because it is a UI-side
concern (spinner around the RMP fan-out) that already has its own
deduping fingerprint cache.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from agents import memory_agent
from agents.planning_agent import run_planning_agent

MEMORY_TOP_K = int(os.environ.get("MEMORY_TOP_K", "4"))

# PII patterns conservatively scrubbed before any retrieved memory is sent
# to Gemini. Matches user emails, SSN-style 9-digit IDs, and phone-like
# 7-15 digit runs. Tuned for false positives over false negatives because
# the prompt only loses *information density* if we over-mask.
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_SSN_RE = re.compile(r"\b\d{3}-?\d{2}-?\d{4}\b")
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d[\d\-\s().]{7,14}\d)(?!\d)")


def _redact_pii(text: str) -> str:
    """Replace likely PII (email/SSN/phone) with neutral placeholders.

    This runs *only* on retrieved memory snippets, not on the user's live
    preference text (the user opted in to that). Course codes like
    ``COEN 174`` and unit counts (``total_units=12``) are short and
    unlikely to look like phone numbers, so the phone regex requires
    8+ digits with separators.
    """
    if not text:
        return ""
    out = _EMAIL_RE.sub("[redacted-email]", text)
    out = _SSN_RE.sub("[redacted-id]", out)
    out = _PHONE_RE.sub("[redacted-phone]", out)
    return out


def _summarize_for_memory(
    missing_details: list[dict], user_preference: str, plan: dict
) -> str:
    """Compress (preference, gap, recommendation) into a short remembered note.

    Format mirrors the spec template (PREF / GAP / PLAN) so retrieval
    queries can hit on simple lexical overlap even when the embedding
    fallback is in use.
    """
    pref = (user_preference or "").strip().replace("\n", " ")
    if len(pref) > 200:
        pref = pref[:197] + "..."

    gap_codes = []
    for item in (missing_details or [])[:5]:
        code = (item or {}).get("course")
        if code:
            gap_codes.append(str(code))

    recommended = plan.get("recommended") or []
    plan_codes = [str(r.get("course", "")).strip() for r in recommended if r]
    plan_codes = [c for c in plan_codes if c]
    total_units = plan.get("total_units")

    return (
        f"PREF: {pref}\n"
        f"GAP: {', '.join(gap_codes)}\n"
        f"PLAN: {', '.join(plan_codes)} | total_units={total_units}"
    )


def _retrieve_snippets(user_id: int, query: str) -> list[str]:
    """Best-effort retrieval; never raises into the planning UI."""
    try:
        rows = memory_agent.retrieve(user_id, query, k=MEMORY_TOP_K)
    except Exception:
        return []
    # Deduplicate identical content while preserving distance ordering, and
    # apply PII redaction before content can reach the model prompt.
    seen: set[str] = set()
    snippets: list[str] = []
    for row in rows:
        content = (row.get("content") or "").strip()
        if not content:
            continue
        cleaned = _redact_pii(content)
        if cleaned in seen:
            continue
        seen.add(cleaned)
        snippets.append(cleaned)
    return snippets


def plan_for_user(
    user_id: int,
    missing_details: list[dict],
    user_preference: str,
    previous_plan: dict | None = None,
) -> dict[str, Any]:
    """End-to-end planning call scoped to one user.

    ``previous_plan`` is the most recent plan the UI already has on screen
    for this student (typically `st.session_state['planning_result']`).
    Passing it makes the planning agent treat ``user_preference`` as a
    follow-up message and produce an explicit ``assistant_reply``
    describing what changed and why.
    """
    if user_id is None:
        raise ValueError("orchestrator.plan_for_user requires user_id")

    gap_codes = ", ".join(
        str((item or {}).get("course") or "") for item in (missing_details or [])[:5]
    )
    # Strip preference for retrieval only so leading/trailing spaces do not change
    # embedding distance to stored notes; the planning prompt still uses the raw text.
    pref_for_retrieve = (user_preference or "").strip()
    query = f"{pref_for_retrieve} | gap: {gap_codes}".strip()

    memory_snippets = _retrieve_snippets(int(user_id), query)

    plan = run_planning_agent(
        missing_details=missing_details,
        user_preference=user_preference,
        memory_snippets=memory_snippets,
        previous_plan=previous_plan,
    )

    # Best-effort write-back; planning success must not depend on memory writes.
    try:
        memory_agent.write(
            user_id=int(user_id),
            kind="plan_outcome",
            content=_summarize_for_memory(missing_details, user_preference, plan),
            meta={
                "total_units": plan.get("total_units"),
                "n_recommended": len(plan.get("recommended") or []),
            },
        )
    except Exception:
        # Logging here would need a logger; for the prototype we silently
        # skip so the user always sees their plan even if RAG persistence
        # is degraded.
        pass

    return plan
