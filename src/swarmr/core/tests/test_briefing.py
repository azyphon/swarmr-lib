"""The first-round briefing rule.

It exists because a prompt instruction was observed failing in a live run: the
orchestrator tailored each round-one briefing per domain, handing specialists a
conclusion — and in one case the exact hypothesis under test — before any of them
had looked at anything.
"""

from __future__ import annotations

from typing import Any, cast

from langchain_core.messages import HumanMessage, ToolMessage

from swarmr.core.briefing import effective_briefing
from swarmr.core.middleware import FirstRoundBriefing


class FakeRequest:
    """Minimal stand-in for ToolCallRequest."""

    def __init__(self, name: str, args: dict[str, Any], state: Any = None) -> None:
        self.tool_call: dict[str, Any] = {"name": name, "args": args, "id": "c1"}
        self.state = state or {"messages": [HumanMessage(content="pods will not start")]}

    def override(self, tool_call: dict[str, Any]) -> FakeRequest:
        clone = FakeRequest(tool_call["name"], tool_call["args"], self.state)
        clone.tool_call = tool_call
        return clone


def passthrough(request: Any) -> ToolMessage:
    args = request.tool_call.get("args") or {}
    return ToolMessage(content=str(args.get("description", "")), tool_call_id="c1")


class TestFirstRoundBriefing:
    def test_first_dispatch_is_replaced_with_the_callers_request(self) -> None:
        mw = FirstRoundBriefing(exempt=("critic",))
        request = FakeRequest(
            "task",
            {"subagent_type": "workload", "description": "check exit codes, probes, ..."},
        )
        assert passthrough_result(mw, request) == "pods will not start"

    def test_second_dispatch_keeps_its_targeted_question(self) -> None:
        mw = FirstRoundBriefing(exempt=("critic",))
        first = FakeRequest("task", {"subagent_type": "workload", "description": "x"})
        passthrough_result(mw, first)
        second = FakeRequest(
            "task", {"subagent_type": "workload", "description": "did web ever start?"}
        )
        assert passthrough_result(mw, second) == "did web ever start?"

    def test_exempt_agents_are_untouched(self) -> None:
        mw = FirstRoundBriefing(exempt=("critic",))
        request = FakeRequest(
            "task", {"subagent_type": "critic", "description": "hypothesis: ..."}
        )
        assert passthrough_result(mw, request) == "hypothesis: ..."

    def test_other_tools_are_untouched(self) -> None:
        mw = FirstRoundBriefing(exempt=())
        request = FakeRequest("k_get", {"kind": "pod"})
        assert passthrough_result(mw, request) == ""


def test_effective_briefing_rule() -> None:
    seen: set[str] = set()
    assert effective_briefing("symptom", "workload", (), seen) == "symptom"
    assert effective_briefing("symptom", "critic", ("critic",), seen) is None
    assert effective_briefing("symptom", "workload", (), {"workload"}) is None
    assert effective_briefing("", "workload", (), seen) is None


def passthrough_result(mw: Any, request: Any) -> str:
    result = mw.wrap_tool_call(cast(Any, request), passthrough)
    return str(getattr(result, "content", ""))
