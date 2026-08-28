"""Terminal entrypoint: run a team with live streaming output.

This is the demo and debugging surface. The MCP server in `server.py` is the
integration surface; both share `core.runner`, so a run behaves identically
either way.

    teams --list                  # what is installed
    teams <team> "the symptom, as prose"
    teams <team>                  # the team's own default request
    teams --target <team>         # profile the target, then exit
"""

from __future__ import annotations

import argparse
import sys

from swarmr.core.runner import run_streamed
from swarmr.core.team import Team, TeamError
from swarmr.teams import get, names

__all__ = ["main"]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="teams",
        description="Run a Deep Agents team of domain specialists.",
    )
    parser.add_argument("team", nargs="?", help=f"one of: {', '.join(names())}")
    parser.add_argument("request", nargs="*", help="the symptom or task, as prose")
    parser.add_argument(
        "--list", action="store_true", help="list registered teams and exit"
    )
    parser.add_argument(
        "--target",
        action="store_true",
        help="profile the team's target and exit without running the agent",
    )
    parser.add_argument("--no-colour", action="store_true", help="disable ANSI colour")
    return parser


def _list_teams() -> int:
    for name in names():
        team = get(name)
        print(f"{team.name}\n  {team.summary}")
        if team.prompt_hint:
            print(f'  e.g. teams {team.name} "{team.prompt_hint}"')
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.list or not args.team:
        return _list_teams()

    try:
        team = get(args.team)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    # Both remaining paths reach into the team's environment — a cluster, a
    # credential, an API — so both can fail for reasons that are the operator's
    # to fix. `TeamError` carries the sentence; anything else is a bug and keeps
    # its traceback.
    try:
        if args.target:
            # `Team.target()` uses the team's own profiler when it has one, so
            # this path talks to the target and nothing else — no model, no API
            # key.
            print(team.target())
            return 0
        return _run(team, args)
    except TeamError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def _run(team: Team, args: argparse.Namespace) -> int:
    """Stream one investigation."""
    # The team owns its default: only it knows what a useful sweep of its own
    # target looks like. A team that declares none gets its example invocation.
    request = team.request_or_default(" ".join(args.request)) or team.prompt_hint
    if not request:
        print(
            f"error: team {team.name!r} declares no default request; "
            "pass the symptom or task as prose",
            file=sys.stderr,
        )
        return 2

    colour = sys.stdout.isatty() and not args.no_colour
    run_streamed(team, request, colour=colour)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
