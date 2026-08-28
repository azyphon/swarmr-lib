"""The team contract: the invariants a misdeclared team used to violate silently.

Two of these are regressions rather than hypotheticals. A half-declared report
pair produced closing prose instead of the filed report, with nothing anywhere
saying so. And `target()` without a profiler builds the graph, which constructs a
model client — so merely asking which cluster you are pointed at needed an API
key.
"""

from __future__ import annotations

from typing import Any

import pytest

from swarmr.core.team import Member


@pytest.mark.parametrize(
    ("report_tool", "render_report"),
    [("file_report", None), ("", lambda args: str(args))],
    ids=["tool-without-renderer", "renderer-without-tool"],
)
def test_team_half_declared_report_pair_is_rejected(
    stub_team: Any, report_tool: str, render_report: Any
) -> None:
    """Half of the pair fails silently: the reader captures a filing only when
    `report_tool` is set, so a renderer alone means the run falls back to prose."""
    with pytest.raises(ValueError, match="must be set together"):
        stub_team(report_tool=report_tool, render_report=render_report)


@pytest.mark.parametrize(
    ("report_tool", "render_report"),
    [("file_report", lambda args: str(args)), ("", None)],
    ids=["both-set", "neither-set"],
)
def test_team_accepts_a_whole_report_pair_or_none(
    stub_team: Any, report_tool: str, render_report: Any
) -> None:
    team = stub_team(report_tool=report_tool, render_report=render_report)
    assert team.report_tool == report_tool


@pytest.mark.parametrize("limit", [0, -1])
def test_team_rejects_a_non_positive_recursion_limit(stub_team: Any, limit: int) -> None:
    """A budget below one cannot run a single step, so it is a declaration error."""
    with pytest.raises(ValueError, match="recursion_limit must be positive"):
        stub_team(recursion_limit=limit)


def test_team_accepts_a_recursion_limit_of_one(stub_team: Any) -> None:
    assert stub_team(recursion_limit=1).recursion_limit == 1


def test_target_uses_the_profile_without_building_the_graph(stub_team: Any) -> None:
    """The bug: asking which target you point at needed a model API key, because
    the only way to get the banner was to build the graph."""
    team = stub_team(profile=lambda: "kind-demo, 3 nodes")
    assert team.target() == "kind-demo, 3 nodes"
    assert stub_team.runs == [], "profiling must not build the agent graph"


def test_target_falls_back_to_the_build_banner(stub_team: Any) -> None:
    """A team without a profiler still answers, by building and reading the banner."""
    team = stub_team()
    assert team.target() == "the target"
    assert len(stub_team.runs) == 1


@pytest.mark.parametrize(
    ("request_text", "expected"),
    [
        ("look at demo", "look at demo"),
        ("  look at demo  ", "look at demo"),
        ("", "the default sweep"),
        ("   \n ", "the default sweep"),
    ],
    ids=["caller-wins", "stripped", "empty-falls-back", "blank-falls-back"],
)
def test_request_or_default_prefers_the_caller(
    stub_team: Any, request_text: str, expected: str
) -> None:
    team = stub_team(default_request="the default sweep")
    assert team.request_or_default(request_text) == expected


def test_request_or_default_is_empty_when_the_team_declares_no_default(
    stub_team: Any,
) -> None:
    """The caller decides what to do about it; the team must not invent a task."""
    assert stub_team().request_or_default("  ") == ""


def test_tool_name_is_derived_from_the_team_name(stub_team: Any) -> None:
    """The MCP tool name is API surface, so it is fixed by the team name."""
    assert stub_team(name="gitops_sync").tool_name == "start_gitops_sync"


def test_roster_aligns_roles_under_the_longest_name(stub_team: Any) -> None:
    team = stub_team(
        members=(
            Member("network", "routing and policy"),
            Member("io", "disks and volumes"),
        )
    )
    lines = team.roster().splitlines()
    pairs = zip(lines, team.members, strict=True)
    columns = [line.index(member.role) for line, member in pairs]
    assert len(set(columns)) == 1, "roles must line up in one column"
    assert lines[0] == "  network  routing and policy"


def test_roster_is_empty_for_a_team_with_no_declared_members(stub_team: Any) -> None:
    """Empty rather than a stray heading: callers concatenate this into output."""
    assert stub_team().roster() == ""
