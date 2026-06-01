"""English-only guidance is prompt-based (no CJK post-filter)."""

from __future__ import annotations

from agents.planning_agent import (
    ENGLISH_ONLY_USER_OUTPUT_RULE,
    _sanitize_model_output,
    filter_freeform_model_text,
)
from agents.planning_agent_llm import _selection_system_instruction


def test_english_only_rule_in_planner_system_instructions():
    assert "English only" in ENGLISH_ONLY_USER_OUTPUT_RULE
    assert ENGLISH_ONLY_USER_OUTPUT_RULE in _selection_system_instruction()


def test_filter_freeform_model_text_passes_chinese_but_blocks_recipe():
    chinese = "好的，我会帮你安排课程。"
    assert filter_freeform_model_text(chinese, fallback="fallback") == chinese
    assert (
        filter_freeform_model_text("warm a tortilla with salsa", fallback="fallback")
        == "fallback"
    )


def test_sanitize_model_output_keeps_chinese_advice_and_reply():
    parsed = _sanitize_model_output(
        {
            "recommended": [
                {
                    "course": "CSEN 174",
                    "title": "Software Engineering",
                    "units": 4,
                    "category": "Major",
                    "reason": "满足毕业要求",
                }
            ],
            "total_units": 4,
            "advice": "下学期建议选四门课。",
            "assistant_reply": "好的，已为你生成计划。",
        }
    )
    assert "下学期" in parsed["advice"]
    assert "好的" in parsed["assistant_reply"]
    assert parsed["recommended"][0]["reason"] == "满足毕业要求"
