"""Renderer output: one dim label per section, no gutter, nothing truncated.

`core` must also render a team it has never heard of, which is the check that no
role name and no payload vocabulary has crept back into the shared layer.
"""

from __future__ import annotations

from typing import Any

from swarmr.core.events import Event, EventKind
from swarmr.core.render import Renderer


def render(
    events: list[Event],
    capsys: Any,
    orchestrator: str = "commander",
    is_error: Any = None,
) -> str:
    view = Renderer(colour=False, orchestrator=orchestrator, is_error=is_error)
    for event in events:
        view.show(event)
    return capsys.readouterr().out


def test_sections_are_labelled_once_without_rule_characters(capsys: Any) -> None:
    output = render(
        [
            Event(EventKind.PLAN, "", "fan out", True, "root"),
            Event(EventKind.DISPATCH, "network", "look at routing", True, "root"),
        ],
        capsys,
    )
    assert "commander" in output
    assert "---" not in output and "===" not in output
    assert output.count("commander") == 1, "the label repeats per speaker, not per line"


def test_header_fields_carry_no_decoration(capsys: Any) -> None:
    """The run header once used "=== team:" while sections used "---"."""
    view = Renderer(colour=False, orchestrator="commander")
    view.field("team", "example")
    view.field("request", "why will reports not start")
    output = capsys.readouterr().out
    assert "===" not in output and "---" not in output
    assert "team     example" in output


def test_prose_has_no_gutter_characters(capsys: Any) -> None:
    output = render(
        [Event(EventKind.VERDICT, "network", "VERDICT: implicated", True, "root")],
        capsys,
    )
    assert "|" not in output
    assert "network reports" in output


def test_dispatch_text_is_not_truncated(capsys: Any) -> None:
    """Dispatch summaries were once cut at 64 characters, mid-sentence."""
    sentence = (
        "Investigate why the reports workload in namespace demo will not start, "
        "covering the last hour of events and both pods."
    )
    output = render(
        [Event(EventKind.DISPATCH, "workload", sentence, True, "root")], capsys
    )
    assert "…" not in output
    for word in sentence.split():
        assert word in output


def test_the_teams_failure_test_decides_the_error_mark(capsys: Any) -> None:
    """Failure wording is domain vocabulary, so the team supplies the test."""
    output = render(
        [Event(EventKind.RESULT, "k_get", "BOOM: unknown kind", False, "a1b2")],
        capsys,
        is_error=lambda text: text.startswith("BOOM"),
    )
    assert output.strip().splitlines()[-1].lstrip().startswith("!")


def test_without_a_failure_test_nothing_is_marked_as_an_error(capsys: Any) -> None:
    """`core` used to match one team's prefixes, which lied for every other."""
    output = render(
        [Event(EventKind.RESULT, "k_get", "tool error: unknown kind 'x'", False, "a1b2")],
        capsys,
    )
    assert output.strip().splitlines()[-1].lstrip().startswith("←")


def test_usage_note_is_printed_by_the_renderer(capsys: Any) -> None:
    """One layer owns stdout: the runner hands over text, it never prints."""
    view = Renderer(colour=False)
    view.note("TOKENS  ...")
    view.note("")
    assert capsys.readouterr().out == "TOKENS  ...\n"


def test_renderer_works_for_an_unknown_team(capsys: Any) -> None:
    """No role table: a foreman and a welder must render as well as a commander."""
    output = render(
        [
            Event(EventKind.PLAN, "", "survey the site", True, "root"),
            Event(EventKind.DISPATCH, "welder", "inspect seam 4", True, "root"),
            Event(EventKind.VERDICT, "welder", "VERDICT: implicated", True, "root"),
        ],
        capsys,
        orchestrator="foreman",
    )
    assert "foreman" in output
    assert "welder reports" in output
