"""Deep Agents middleware: the only place `core` touches the agent framework.

Two adapters, both harness-facing:

  * `AnnounceName` binds a subagent's stream to its name, so the trail can say
    "network" instead of "[a1b2]".
  * `FirstRoundBriefing` replaces each subagent's first briefing with the
    caller's own request; the rule it enforces is `core.briefing`.

They live together because they are the same kind of thing — a LangChain
`AgentMiddleware` implementation — and because keeping them out of the modules
that state the rules leaves those modules importable without the framework.
Nothing here is domain-aware.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langchain.agents.middleware.types import AgentMiddleware, ToolCallRequest
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from swarmr.core.attribution import Attribution
from swarmr.core.briefing import effective_briefing
from swarmr.core.harness import DESCRIPTION_KEY, SUBAGENT_KEY, TASK_TOOL

__all__ = ["AnnounceName", "FirstRoundBriefing"]


class AnnounceName(AgentMiddleware):
    """Register a subagent's name against its stream before it calls a tool.

    Attribution used to land only when a tool *executed*, while the tool call is
    displayed the moment the model emits it — so each specialist's first line
    showed a raw stream id and appeared under a separate heading. A model call
    always precedes that subagent's tool calls, so announcing here means the
    very first line is attributed.

    The name is passed in rather than read from metadata: the team already knows
    it, and one fewer dependency on an undocumented field is worth having. The
    `Attribution` is passed in too, which is what keeps it per run.
    """

    def __init__(self, agent_name: str, attribution: Attribution) -> None:
        super().__init__()
        self.agent_name = agent_name
        self.attribution = attribution

    @property
    def name(self) -> str:
        # A property, not a class attribute: the installed AgentMiddleware
        # declares `name` as a property, unlike some upstream examples.
        return f"AnnounceName[{self.agent_name}]"

    def wrap_model_call(self, request: Any, handler: Any) -> Any:
        self.attribution.note(self.agent_name)
        return handler(request)


class FirstRoundBriefing(AgentMiddleware):
    """Replace the first briefing of each subagent with the caller's request.

    The reasoning is in `core.briefing`; this is the enforcement point.

    Args:
        exempt: Subagents whose payload must be passed through, typically the
            adjudicator, which receives a hypothesis rather than a symptom.
    """

    def __init__(self, exempt: tuple[str, ...] = ()) -> None:
        super().__init__()
        self.exempt = exempt
        self._briefed: set[str] = set()

    @property
    def name(self) -> str:
        return "FirstRoundBriefing"

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command[Any]],
    ) -> ToolMessage | Command[Any]:
        call = request.tool_call
        if call.get("name") != TASK_TOOL:
            return handler(request)

        args = dict(call.get("args") or {})
        who = str(args.get(SUBAGENT_KEY, ""))
        symptom = effective_briefing(
            _caller_request(request.state), who, self.exempt, self._briefed
        )
        self._briefed.add(who)
        if symptom is None:
            return handler(request)

        args[DESCRIPTION_KEY] = symptom
        return handler(request.override(tool_call={**call, "args": args}))


def _caller_request(state: Any) -> str:
    """The original human request, which is the only unbiased symptom available."""
    messages = state.get("messages") if isinstance(state, dict) else None
    for message in messages or []:
        if getattr(message, "type", "") == "human":
            content = getattr(message, "content", "")
            if isinstance(content, str) and content.strip():
                return content.strip()
    return ""
