"""Discovery: how installed teams are found, and what listing them may cost.

These are the properties the plug-in seam rests on. Listing must not import a
team, because the MCP server lists on every start; a declared lazy target must
resolve, because moving an import into a string moves a typo from import time to
run time; and an entry point that is not a `Team` must fail by name, because
that is the one mistake an out-of-tree package can make.

Core ships no team, so discovery is exercised against an injected entry point
rather than an installed one. That is not a compromise: it is the same path a
third-party distribution takes, and testing it this way is what proves core
stands alone. The complementary half — that a *real* installed team is found and
stays unimported until run — belongs to the team's own suite, where the team
exists.
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
from dataclasses import fields
from importlib.metadata import EntryPoint

import pytest

from swarmr.cli import main as cli_main
from swarmr.core.jobs import JobStore
from swarmr.core.team import Lazy, Team
from swarmr.core.testing import EXAMPLE_TEAM
from swarmr.server import build_server
from swarmr.teams import GROUP, get, names

EXAMPLE = EntryPoint(
    name="example", value="swarmr.core.testing:EXAMPLE_TEAM", group=GROUP
)


@pytest.fixture
def one_team(monkeypatch: pytest.MonkeyPatch) -> None:
    """Registry holding exactly one team, injected the way a distribution would."""
    monkeypatch.setattr("swarmr.teams.entry_points", lambda group: (EXAMPLE,))


@pytest.fixture
def no_teams(monkeypatch: pytest.MonkeyPatch) -> None:
    """Core as installed on its own: nothing advertises the group."""
    monkeypatch.setattr("swarmr.teams.entry_points", lambda group: ())


class TestDiscovery:
    def test_an_advertised_team_is_listed(self, one_team: None) -> None:
        assert names() == ["example"]

    def test_every_registered_name_loads_a_team(self, one_team: None) -> None:
        assert all(isinstance(get(name), Team) for name in names())

    def test_a_name_resolves_to_the_advertised_object(self, one_team: None) -> None:
        assert get("example") is EXAMPLE_TEAM

    def test_unknown_team_names_the_alternatives(self, one_team: None) -> None:
        with pytest.raises(ValueError, match=r"unknown team 'nope'.*example"):
            get("nope")

    def test_an_entry_point_that_is_not_a_team_is_rejected_by_name(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The ABI boundary: `core` must not hand a stranger to the runner."""
        bogus = EntryPoint(name="bogus", value="swarmr.core.text:clip", group=GROUP)
        monkeypatch.setattr("swarmr.teams.entry_points", lambda group: (bogus,))
        with pytest.raises(TypeError, match=r"'bogus'.*is not a Team"):
            get("bogus")

    def test_removing_the_last_team_leaves_working_surfaces(
        self, no_teams: None, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Uninstalling a team must not break the CLI or the MCP server.

        Deleting a team is meant to be one deletion, which is only true if the
        surfaces tolerate an empty registry instead of publishing a tool for a
        team that is gone. Since the split this is also core's own resting
        state, so it is the shape a fresh `pip install swarmr` must survive.
        """
        assert names() == []
        assert cli_main(["--list"]) == 0
        assert cli_main(["ghost"]) == 2
        assert "Available teams: none" in capsys.readouterr().err
        published = asyncio.run(build_server(JobStore()).list_tools())
        assert not [t.name for t in published if t.name.startswith("start_")]


class TestLazyFields:
    def test_every_declared_target_resolves_to_something_callable(
        self, one_team: None
    ) -> None:
        """A string target is only as good as this check.

        Imports each team's implementation, which is exactly what the listing
        path avoids — appropriate here and nowhere else.
        """
        for name in names():
            team = get(name)
            declared = (getattr(team, f.name) for f in fields(team))
            targets = [f.target for f in declared if isinstance(f, Lazy)]
            # No team is required to defer anything; a team's own contract test
            # pins which of its fields must be lazy.
            for target in targets:
                assert callable(Lazy(target).resolve()), target

    def test_nothing_is_imported_before_the_first_call(self) -> None:
        with pytest.raises(ModuleNotFoundError):
            Lazy("swarmr.no_such_module:thing")()

    def test_a_non_callable_target_is_refused(self) -> None:
        with pytest.raises(TypeError, match="not callable"):
            Lazy("swarmr.teams:GROUP").resolve()

    def test_arguments_and_result_pass_straight_through(self) -> None:
        clip = Lazy("swarmr.core.text:clip")
        assert clip("abcdef ghi", limit=7) == "abcdef…"


def test_publishing_the_mcp_surface_stays_cheap() -> None:
    """The startup cost claim, measured where it is made.

    A subprocess because this process has imported a good deal for other tests,
    and the point is what a fresh server loads. Core alone can only prove its
    own half — that publishing costs little. That no *team* implementation is
    imported is proven in the team's suite, which is the only place a team to
    not-import exists.
    """
    probe = (
        "import sys\n"
        "from swarmr.server import build_server\n"
        "build_server()\n"
        "print(len(sys.modules))\n"
    )
    done = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, check=True
    )
    # Guards the order of magnitude, not a number to chase: the whole agent
    # stack is ~4500 modules, and a listing that stays under a thousand cannot
    # have loaded it.
    assert int(done.stdout.strip()) < 1500, done.stdout
