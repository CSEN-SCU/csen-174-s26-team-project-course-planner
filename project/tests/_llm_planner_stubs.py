"""Shared stubs for tests that exercise ``orchestrator.plan_for_user`` / ``run_llm_planner``.

The production orchestrator calls ``planning_agent_llm.run_llm_planner``, not
``planning_agent.run_planning_agent``. Patch the LLM module's client and xlsx
loaders so tests stay offline and never require a real ``GEMINI_API_KEY``.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

from agents import planning_agent_llm as llm_mod


def _schedule_index_for_codes(*codes: str) -> dict:
    index: dict = {}
    for code in codes:
        code = str(code).strip()
        if not code or " " not in code:
            continue
        subj, num = code.split(None, 1)
        index[(subj, num)] = {
            "instructors": [],
            "meeting_days": [],
            "meeting_start_min": None,
            "meeting_end_min": None,
        }
    return index


def patch_llm_planner(
    monkeypatch,
    captured_prompts: list[str],
    reply: dict[str, Any],
    *,
    extra_codes: tuple[str, ...] = (),
) -> None:
    """Stub Gemini + schedule loaders for ``run_llm_planner`` prompt assertions."""
    codes: set[str] = set(extra_codes)
    for item in reply.get("recommended") or []:
        if isinstance(item, dict) and item.get("course"):
            codes.add(str(item["course"]))

    schedule_index = _schedule_index_for_codes(*codes)
    titles = {
        key: f"Title {key[0]} {key[1]}"
        for key in schedule_index
    }
    units = {key: 4 for key in schedule_index}
    offered = [
        {"course": f"{subj} {num}", "title": titles[(subj, num)], "units": 4}
        for subj, num in schedule_index
    ]

    class _StubModels:
        def generate_content(self, model, contents, config):  # noqa: D401
            captured_prompts.append(contents)
            return SimpleNamespace(text=json.dumps(reply))

    class _StubClient:
        models = _StubModels()

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(llm_mod, "get_genai_client", lambda *, purpose: _StubClient())
    monkeypatch.setattr(llm_mod, "load_schedule_section_index", lambda: schedule_index)
    monkeypatch.setattr(llm_mod, "load_category_course_index", lambda: {})
    monkeypatch.setattr(llm_mod, "load_course_titles_index", lambda: titles)
    monkeypatch.setattr(llm_mod, "load_course_units_index", lambda: units)
    monkeypatch.setattr(llm_mod, "list_offered_courses", lambda: offered)
    monkeypatch.setattr(llm_mod, "load_all_course_sections", lambda: {})

    import utils.major_requirements as mr

    monkeypatch.setattr(mr, "build_major_advisor_block", lambda **kw: ("", "csen"))
