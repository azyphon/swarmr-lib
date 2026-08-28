"""Team discovery: how everything else finds the teams that are installed.

A team is a package that declares a `Team` and advertises it in the
`swarmr.teams` entry-point group:

    [project.entry-points."swarmr.teams"]
    k8s_incident = "my_package:TEAM"

Nothing else. There is no list to edit, so adding a team means adding a package
and removing one means deleting it — two teams can be built in parallel without
meeting in a shared file, and a team living in its own distribution plugs in the
same way as one shipped here.

Entry points are metadata, not imports: `names()` reads the installed
distributions and loads no team code. Resolution happens in `get`, so a team's
import cost is paid only by whoever runs it. That cost is real — for the
incident team the Kubernetes client, the model SDK and the whole agent stack,
measured at 4533 modules — and it is why a team's declaration keeps its
heavyweight fields behind `core.team.Lazy`.

The `Team` check in `get` is the ABI boundary: it is the one thing an
out-of-tree package can get wrong, so the error names the offending entry.
"""

from __future__ import annotations

from importlib.metadata import EntryPoint, entry_points

from swarmr.core.team import Team

__all__ = ["GROUP", "get", "names"]

GROUP = "swarmr.teams"


def _registered() -> dict[str, EntryPoint]:
    """Every advertised team, by name. Imports no team."""
    return {entry.name: entry for entry in entry_points(group=GROUP)}


def names() -> list[str]:
    """Every registered team name. Imports nothing."""
    return sorted(_registered())


def get(name: str) -> Team:
    """Look up and load a team, with an actionable error rather than a KeyError."""
    try:
        entry = _registered()[name]
    except KeyError:
        raise ValueError(
            f"unknown team {name!r}. Available teams: {', '.join(names()) or 'none'}"
        ) from None
    team = entry.load()
    if not isinstance(team, Team):
        raise TypeError(
            f"entry point {entry.name!r} -> {entry.value!r} is not a Team; "
            f"it resolved to {type(team).__name__}"
        )
    return team
