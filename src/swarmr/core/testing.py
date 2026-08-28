"""Stubs for testing against the `core` contract, without a model.

Shipped rather than kept in a test directory because they belong to the
contract: a team — including one in its own distribution — needs the same
`Team` and `Job` stand-ins to test what it hands `core`, and a copy in each
place would drift from the contract it is meant to mirror.

Nothing here imports pytest. The fixtures that wrap these live in the repo's
root `conftest.py`, so this module stays importable as ordinary code.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from typing import Any

from swarmr.core.jobs import Job
from swarmr.core.team import RunContext, Team, TeamBuild

__all__ = ["EXAMPLE_TEAM", "Chunk", "GraphStub", "JobFactory", "TeamFactory"]

# (namespace, stream mode, payload) — one chunk as LangGraph yields it with
# stream_mode=["updates", "values"] and subgraphs=True.
Chunk = tuple[tuple[str, ...], str, dict[str, Any]]


class GraphStub:
    """A compiled graph that replays a fixed chunk list.

    Mirrors the exact `stream` call the runner makes, so a test exercises the
    real stream loop, reader and report selection with no model behind it.
    """

    def __init__(self, chunks: Sequence[Chunk]) -> None:
        self.chunks = list(chunks)

    def stream(
        self,
        _input: Any,
        _config: Any,
        stream_mode: Any = None,
        subgraphs: bool = False,
    ) -> Iterator[Chunk]:
        return iter(self.chunks)


@dataclass(slots=True)
class TeamFactory:
    """Builds stub teams, recording every build the code under test performed.

    `runs` is the point of the recording: several contracts are about *not*
    building. `Team.target()` on a team with a profiler must not construct a
    graph, because building constructs a model client and so needs an API key.
    """

    runs: list[RunContext] = field(default_factory=list)

    def __call__(self, chunks: Sequence[Chunk] = (), **overrides: Any) -> Team:
        graph = GraphStub(chunks)

        def build(run: RunContext) -> TeamBuild:
            self.runs.append(run)
            return TeamBuild(graph=graph, banner="the target")

        fields: dict[str, Any] = {
            "name": "stub",
            "summary": "s",
            "description": "d",
            "build": build,
            "report_tool": "file_report",
            "render_report": lambda args: f"ROOT CAUSE\n{args['root_cause']}",
        }
        return Team(**(fields | overrides))


@dataclass(slots=True)
class JobFactory:
    """Builds jobs with distinct ids, so a store holds several of them."""

    created: int = 0

    def __call__(self, **overrides: Any) -> Job:
        self.created += 1
        fields: dict[str, Any] = {
            "id": f"j{self.created}",
            "team": "stub",
            "request": "r",
        }
        return Job(**(fields | overrides))


# A module-level `Team`, which `TeamFactory` cannot be: an entry point names its
# target as a string, so testing discovery at all needs one importable Team
# object. Core ships no real team, so without this the registry tests would have
# to depend on some team being installed — the exact coupling the split removes.
# Doubles as the smallest complete example of the ABI an out-of-tree team
# implements.
EXAMPLE_TEAM = TeamFactory()(name="example", summary="an example team")
