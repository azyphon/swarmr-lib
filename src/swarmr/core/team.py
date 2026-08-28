"""The contract every team implements.

This is the only thing `core` knows about a team, and it is deliberately
domain-free: a team hands back a compiled Deep Agent graph plus a one-line
banner describing the target it just profiled. Nothing Kubernetes-shaped,
Terraform-shaped or cloud-shaped may appear here, because that is what keeps a
team deletable — delete its package and nothing in the tree refers to it.

Everything `core` would otherwise have to assume lives on `Team` as a field: the
name of root-level activity, how to summarise a payload, what counts as a tool
failure, how deep the graph may recurse, what to run when the caller names no
task. A default is supplied for each, so declaring a team stays short, but no
default encodes a domain.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from importlib import import_module
from typing import Any, Protocol

from swarmr.core.attribution import Attribution

__all__ = [
    "Lazy",
    "Member",
    "RunContext",
    "Team",
    "TeamBuild",
    "TeamBuilder",
    "TeamError",
]


class TeamError(RuntimeError):
    """A run cannot start, and the reason is for the operator to act on.

    Raised by a team from `build` or `profile` when the environment is wrong
    rather than the code: a missing or expired credential, an unreachable
    target, an ambiguous choice the team refuses to guess at. `core` knows
    nothing about the cause, only that the message is a sentence to print
    rather than a stack to dump — so both surfaces render it as one line, the
    CLI on stderr and the MCP job as its failure reason.

    Anything else escaping a team is a bug, and a bug should keep its
    traceback.
    """


@dataclass(frozen=True, slots=True)
class RunContext:
    """Per-run state a team must wire into the graph it builds.

    Attributes:
        attribution: The run's stream-tag -> subagent-name map. Teams pass it to
            `AnnounceName` for each subagent. It is per run, not global, so two
            investigations started over MCP cannot overwrite each other's
            attribution — which is exactly what a module-level map did.
    """

    attribution: Attribution = field(default_factory=Attribution)


@dataclass(frozen=True, slots=True)
class Member:
    """One specialist in a team, for display only.

    The graph is built from the team's own module; this is what a caller sees so
    it knows who is on the roster before any work happens. Keeping it declarative
    means the MCP surface can name the specialists without importing the graph.
    """

    name: str
    role: str


@dataclass(frozen=True, slots=True)
class TeamBuild:
    """What a team returns once it has inspected its target.

    Attributes:
        graph: The compiled Deep Agent, ready for `.invoke` or `.stream`.
        banner: One line describing the live target, shown before the run and
            returned in MCP metadata. Teams profile their own target, so only
            the team can write this.
    """

    graph: Any
    banner: str


class TeamBuilder(Protocol):
    """Builds a team's agent graph. Called once per run, never cached.

    Profiling happens inside the build so every run reflects the target's
    current state rather than whatever was true at import time. The `RunContext`
    carries the state that must not be shared between runs.
    """

    def __call__(self, run: RunContext) -> TeamBuild: ...


@dataclass(frozen=True, slots=True)
class Team:
    """A registered team.

    Attributes:
        name: Stable identifier, snake_case. Forms the MCP tool name, so it is
            API surface: renaming it breaks callers.
        summary: One sentence shown in tool listings.
        description: What the calling model reads to decide whether to route
            here. This does the routing work, so it must state the symptoms and
            questions the team handles, not just its subject area.
        build: Constructs the graph.
        profile: Describes the live target without building anything. Optional,
            but a team that supplies it can be pointed at a target and asked
            "what am I looking at" for free — no model, no API key, no graph.
            `build` profiles too; this is the same answer without the cost.
        default_request: What to run when the caller names no task. The team
            owns this: only it knows what a useful default sweep of its own
            target looks like.
        members: The specialists on the roster, for display. Lets a caller see
            who will work the problem before anything runs.
        prompt_hint: Example invocation, used in generated docs and MCP tool
            descriptions.
        report_tool: Name of the tool whose arguments are the final report.
        render_report: Renders those arguments as text. Set both or neither:
            a renderer without a tool name is dead code, and a tool name
            without a renderer files a raw dict at the caller.
        orchestrator: What to call root-level activity in output, e.g.
            "commander". Display only.
        audit_agents: Members whose dispatched payload is a finished argument
            rather than a symptom — an adjudicator, a reviewer. Their briefings
            are echoed verbatim so the adjudication can be audited, and are
            never replaced by the first-round briefing rule.
        digest: Summarises one of this team's tool results in a line. Only the
            team knows what its payloads mean; without it `core` reports shape
            alone.
        is_error: Whether a tool result is a failure. Failure looks different in
            every domain — one team's tools say "tool error", another's say
            "ERROR" or return an empty list — so `core` cannot recognise one and
            does not guess. Without this every result renders as a plain result.
        recursion_limit: LangGraph recursion budget for one run. A property of
            the team's fan-out, not of the harness: six specialists and twelve
            need different ceilings.
    """

    name: str
    summary: str
    description: str
    build: TeamBuilder
    profile: Callable[[], str] | None = None
    default_request: str = ""
    members: tuple[Member, ...] = ()
    prompt_hint: str = ""
    report_tool: str = ""
    render_report: Callable[[dict[str, Any]], str] | None = None
    # Vocabulary. `core` renders and records; it never assumes a role exists.
    orchestrator: str = "orchestrator"
    audit_agents: tuple[str, ...] = ()
    digest: Callable[[str], str] | None = None
    is_error: Callable[[str], bool] | None = None
    recursion_limit: int = 160

    def __post_init__(self) -> None:
        """Reject a team that cannot work as declared.

        The report pair is checked because getting it half right fails silently:
        the reader only captures a filing when `report_tool` is set, so a team
        that supplied a renderer and forgot the name would fall back to closing
        prose — the exact failure the filed report exists to prevent — with
        nothing anywhere saying so.
        """
        if bool(self.report_tool) != bool(self.render_report):
            raise ValueError(
                f"team {self.name!r}: report_tool and render_report must be set "
                "together; one without the other is silently ignored"
            )
        if self.recursion_limit < 1:
            raise ValueError(f"team {self.name!r}: recursion_limit must be positive")

    @property
    def tool_name(self) -> str:
        return f"start_{self.name}"

    def target(self) -> str:
        """One line describing the live target.

        Uses `profile` when the team has one and falls back to building the
        graph, which profiles as a side effect. The distinction is not cosmetic:
        building constructs a model client, so without `profile` merely asking
        what the target is requires a model API key.
        """
        if self.profile is not None:
            return self.profile()
        return self.build(RunContext()).banner

    def request_or_default(self, request: str) -> str:
        """The request to run: the caller's, else the team's own default."""
        return request.strip() or self.default_request

    def roster(self) -> str:
        """The team's line-up as text, for tool output."""
        if not self.members:
            return ""
        width = max(len(m.name) for m in self.members)
        return "\n".join(f"  {m.name:<{width}}  {m.role}" for m in self.members)


@dataclass(frozen=True, slots=True)
class Lazy:
    """A team field whose implementation is imported on first call.

    `target` is `"module:attribute"`, and the attribute must be callable.

    Declaring a team has to stay cheap. Every consumer that only lists teams —
    `teams --list`, and the MCP server, which needs `name`, `summary` and
    `description` to publish one tool per team — would otherwise import each
    team's graph, model SDK and domain client to read three strings. Deferring
    the heavyweight fields makes that cost proportional to the teams you run
    rather than to the teams you have installed: for the incident team, 4533
    modules at declaration time became 133.

    The import happens on the first call and is then held by `sys.modules`, so a
    run pays it once. A class rather than a closure because the target is worth
    reading: it appears in `repr`, and a test can resolve every declared target
    without calling it — the one check that a moved import still points
    somewhere real.
    """

    target: str

    def resolve(self) -> Callable[..., Any]:
        """Import and return the target, without calling it."""
        module, _, attribute = self.target.partition(":")
        found = getattr(import_module(module), attribute)
        if not callable(found):
            raise TypeError(f"lazy target {self.target!r} is not callable")
        return found

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self.resolve()(*args, **kwargs)
