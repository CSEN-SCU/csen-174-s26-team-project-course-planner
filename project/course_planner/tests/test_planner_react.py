"""Tests for the tool-calling (ReAct) planner.

Stubs the Gemini client to emit function-call turns then a final JSON
answer, and asserts: tools get invoked, results feed back, the loop
terminates, and the final plan parses. No real Gemini, no xlsx I/O.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from agents.multi_agent import planner_react as pr


# ── Fake Gemini response objects ─────────────────────────────────────────────


class _FakeFunctionCall:
    def __init__(self, name, args):
        self.name = name
        self.args = args


def _resp_with_calls(*calls):
    """A response whose .function_calls is populated (model wants tools)."""
    fcs = [_FakeFunctionCall(n, a) for (n, a) in calls]
    # candidates[0].content must exist for the loop to append it.
    content = SimpleNamespace(role="model", parts=[SimpleNamespace(function_call=f) for f in fcs])
    return SimpleNamespace(
        function_calls=fcs,
        text="",
        candidates=[SimpleNamespace(content=content)],
    )


def _resp_final(plan: dict):
    """A response with no function calls — the final JSON answer."""
    return SimpleNamespace(
        function_calls=[],
        text=json.dumps(plan),
        candidates=[SimpleNamespace(content=SimpleNamespace(role="model", parts=[]))],
    )


class _ScriptedModels:
    """Returns queued responses in order; records every call's tool config."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    def generate_content(self, model, contents, config):
        self.calls += 1
        return self._responses[min(self.calls - 1, len(self._responses) - 1)]


def _client(responses):
    return SimpleNamespace(models=_ScriptedModels(responses))


@pytest.fixture(autouse=True)
def stub_tools(monkeypatch):
    """Stub the 3 tools so the loop is offline + deterministic."""
    monkeypatch.setattr(
        pr, "tool_search_schedule",
        lambda subject=None: [{"course": "CSEN 122", "title": "Computer Architecture"}],
    )
    monkeypatch.setattr(
        pr, "tool_get_open_req_candidates",
        lambda req: {"label": "rtc 3", "candidates": [{"course": "SCTR 128"}]},
    )
    monkeypatch.setattr(pr, "tool_get_lab_partner", lambda code: code + "L" if code == "CSEN 122" else None)
    # Re-point the dispatch table at the stubbed callables.
    monkeypatch.setattr(
        pr, "_TOOL_DISPATCH",
        {
            "search_schedule": lambda a: pr.tool_search_schedule(a.get("subject")),
            "get_open_req_candidates": lambda a: pr.tool_get_open_req_candidates(a.get("requirement_text", "")),
            "get_lab_partner": lambda a: pr.tool_get_lab_partner(a.get("course_code", "")),
        },
    )


# ── Tests ────────────────────────────────────────────────────────────────────


def test_no_tools_returns_final_answer_immediately():
    """Model emits final JSON on turn 1 — no tools needed."""
    plan = {"recommended": [{"course": "CSEN 122", "units": 4}]}
    client = _client([_resp_final(plan)])
    out, tool_calls = pr.run_planner_react("plan please", model="x", client=client)
    assert out == plan
    assert tool_calls == []
    assert client.models.calls == 1


def test_single_tool_call_then_final():
    """Model calls search_schedule, gets results, then emits the plan."""
    client = _client([
        _resp_with_calls(("search_schedule", {"subject": "CSEN"})),
        _resp_final({"recommended": [{"course": "CSEN 122", "units": 4}]}),
    ])
    out, tool_calls = pr.run_planner_react("plan", model="x", client=client)
    assert [t["name"] for t in tool_calls] == ["search_schedule"]
    assert tool_calls[0]["args"] == {"subject": "CSEN"}
    assert out["recommended"][0]["course"] == "CSEN 122"
    assert client.models.calls == 2


def test_multiple_tools_in_one_turn():
    """A single model turn can request several tools; all execute."""
    client = _client([
        _resp_with_calls(
            ("search_schedule", {"subject": "CSEN"}),
            ("get_lab_partner", {"course_code": "CSEN 122"}),
            ("get_open_req_candidates", {"requirement_text": "Core: ENGR: RTC 3"}),
        ),
        _resp_final({"recommended": []}),
    ])
    out, tool_calls = pr.run_planner_react("plan", model="x", client=client)
    names = {t["name"] for t in tool_calls}
    assert names == {"search_schedule", "get_lab_partner", "get_open_req_candidates"}


def test_loop_is_bounded_by_max_turns(monkeypatch):
    """If the model NEVER stops calling tools, the loop still terminates."""
    monkeypatch.setattr(pr, "MAX_TOOL_TURNS", 3)
    # Always returns a tool call → would loop forever without the bound.
    always_call = _resp_with_calls(("search_schedule", {}))
    final = _resp_final({"recommended": [{"course": "CSEN 122", "units": 4}]})
    # Queue: 3 tool-call turns, then the forced final no-tools call.
    client = _client([always_call, always_call, always_call, final])
    out, tool_calls = pr.run_planner_react("plan", model="x", client=client)
    # 3 ReAct turns + 1 forced final = 4 model calls.
    assert client.models.calls == 4
    assert len(tool_calls) == 3
    assert out["recommended"][0]["course"] == "CSEN 122"


def test_unknown_tool_name_is_handled():
    """A hallucinated tool name doesn't crash — it returns an error result."""
    client = _client([
        _resp_with_calls(("not_a_real_tool", {})),
        _resp_final({"recommended": []}),
    ])
    out, tool_calls = pr.run_planner_react("plan", model="x", client=client)
    assert tool_calls[0]["name"] == "not_a_real_tool"
    assert out == {"recommended": []}


def test_tool_exception_is_caught(monkeypatch):
    """If a tool raises, the loop captures the error and keeps going."""
    def _boom(a):
        raise RuntimeError("tool exploded")

    monkeypatch.setitem(pr._TOOL_DISPATCH, "search_schedule", _boom)
    client = _client([
        _resp_with_calls(("search_schedule", {})),
        _resp_final({"recommended": [{"course": "CSEN 122", "units": 4}]}),
    ])
    out, _ = pr.run_planner_react("plan", model="x", client=client)
    # Loop survived the tool exception and still produced a plan.
    assert out["recommended"][0]["course"] == "CSEN 122"


def test_markdown_fenced_final_json_is_parsed():
    """Final answer wrapped in ```json fences still parses."""
    fenced = SimpleNamespace(
        function_calls=[],
        text='```json\n{"recommended": [{"course": "CSEN 122", "units": 4}]}\n```',
        candidates=[SimpleNamespace(content=SimpleNamespace(role="model", parts=[]))],
    )
    client = _client([fenced])
    out, _ = pr.run_planner_react("plan", model="x", client=client)
    assert out["recommended"][0]["course"] == "CSEN 122"


def test_unparseable_final_returns_empty_plan():
    bad = SimpleNamespace(
        function_calls=[],
        text="sorry, I cannot help with that",
        candidates=[SimpleNamespace(content=SimpleNamespace(role="model", parts=[]))],
    )
    client = _client([bad])
    out, _ = pr.run_planner_react("plan", model="x", client=client)
    assert out == {"recommended": []}


def test_function_declarations_cover_all_three_tools():
    names = {fd.name for fd in pr._FUNCTION_DECLARATIONS}
    assert names == {"search_schedule", "get_open_req_candidates", "get_lab_partner"}
