"""Snapshot formatting: everything an MCP caller ever sees of a run.

A poll returns this text and nothing else, so a missing section is invisible
work and a stray instruction is a lie. Two things are pinned hard: that a
finished run shows its report or its error, and that `core` emits no polling
instructions of its own — the footer belongs to the calling surface, because
naming a tool here would leave the shared layer advertising a tool that a rename
had already removed.
"""

from __future__ import annotations

from typing import Any

import pytest

from swarmr.core.report import (
    format_roster,
    format_snapshot,
    format_snapshot_line,
    format_usage,
)

FOOTER = "Still running. Poll again with check_task(job='j1')."


def snapshot(**overrides: Any) -> dict[str, Any]:
    """A running snapshot with the fields `Job.snapshot` always supplies."""
    base: dict[str, Any] = {
        "job": "j1",
        "team": "stub",
        "request": "why does payments return 502",
        "state": "running",
        "elapsed_seconds": 12.5,
        "milestone": 3,
        "trail_cursor": 9,
    }
    return base | overrides


def usage_report(**overrides: Any) -> dict[str, Any]:
    """A usage snapshot as `UsageTracker.snapshot` produces it: biggest first."""
    base: dict[str, Any] = {
        "per_agent": {
            "critic": {
                "calls": 4,
                "input": 120_000,
                "output": 8_000,
                "reasoning": 0,
                "cached": 0,
                "total": 128_000,
            },
            "network": {
                "calls": 2,
                "input": 900,
                "output": 100,
                "reasoning": 0,
                "cached": 0,
                "total": 1_000,
            },
        },
        "total_tokens": 129_000,
        "model_calls": 6,
        "langsmith": False,
    }
    return base | overrides


def test_lookup_error_short_circuits_every_other_section() -> None:
    """An unknown job has no state to render, so the error is the whole answer."""
    out = format_snapshot(snapshot(lookup_error="unknown job 'nope'. Known jobs: j1"))
    assert out == "unknown job 'nope'. Known jobs: j1"


def test_header_carries_the_identity_state_and_progress_of_the_job() -> None:
    header = format_snapshot(snapshot()).splitlines()[0]
    assert header == "stub job j1 · running · 12.5s · milestone=3"


def test_target_is_shown_on_its_own_line_under_the_header() -> None:
    """What is being investigated, available before the first token."""
    header = "stub job j1 · running · 12.5s · milestone=3"
    lines = format_snapshot(snapshot(target="kind-demo, 3 nodes")).splitlines()
    assert lines[:2] == [header, "kind-demo, 3 nodes"]


def test_header_omits_the_target_line_until_the_team_has_profiled_it() -> None:
    assert format_snapshot(snapshot()).splitlines()[0].endswith("milestone=3")


def test_waiting_on_names_the_specialists_still_in_flight() -> None:
    """Without it a working run is indistinguishable from a hung one."""
    out = format_snapshot(snapshot(waiting_on=["network", "storage"]))
    assert "waiting on: network, storage" in out.splitlines()[0]


@pytest.mark.parametrize(
    ("is_delta", "expected"),
    [
        (False, "DELEGATION  (1 of 12 steps)"),
        (True, "NEW ACTIVITY since your last poll  (1 of 12 steps)"),
    ],
    ids=["full-trail", "delta"],
)
def test_the_trail_heading_says_whether_it_is_the_whole_trail_or_only_what_is_new(
    is_delta: bool, expected: str
) -> None:
    """A poll that resends seen steps pushes the new ones past the client's
    display cutoff, so a delta must announce itself as one. The count is shown
    for both: a full trail is capped at the deque length, not at the run."""
    out = format_snapshot(
        snapshot(
            trail=[("network", "k_get(kind=svc)")],
            trail_is_delta=is_delta,
            trail_total=12,
        )
    )
    assert expected in out


def test_delta_trail_with_nothing_new_says_so_rather_than_showing_nothing() -> None:
    """Silence reads as a hung run; "none yet" reads as a run still thinking."""
    out = format_snapshot(snapshot(trail_is_delta=True, trail_total=9))
    assert "NEW ACTIVITY since your last poll: none yet." in out


def test_consecutive_steps_are_grouped_under_one_heading_per_actor() -> None:
    """The same layout the terminal uses, rather than a tag on every line."""
    out = format_snapshot(
        snapshot(
            trail=[
                ("commander", "-> network: routing"),
                ("network", "k_get(kind=svc)"),
                ("network", "k_get(kind=ep)"),
            ]
        )
    )
    body = out.splitlines()[out.splitlines().index("DELEGATION") + 1 :]
    assert body == [
        "commander",
        "  -> network: routing",
        "network",
        "  k_get(kind=svc)",
        "  k_get(kind=ep)",
    ]


def test_verdicts_are_listed_with_their_headlines() -> None:
    out = format_snapshot(
        snapshot(verdicts={"network": "implicated", "storage": "cleared"})
    )
    assert "VERDICTS" in out
    assert "  network    implicated" in out
    assert "  storage    cleared" in out


def test_tool_call_counters_are_summarised_on_one_line() -> None:
    out = format_snapshot(snapshot(tool_calls={"k_get": 12, "k_logs": 3}))
    assert "TOOL CALLS  k_get x12, k_logs x3" in out


def test_a_finished_run_ends_with_its_report() -> None:
    out = format_snapshot(snapshot(state="done", report="ROOT CAUSE\ntargetPort"))
    assert out.endswith("\nREPORT\nROOT CAUSE\ntargetPort")


def test_a_finished_run_with_no_report_text_still_reads_as_finished() -> None:
    """An empty report used to fall through to the "still running" footer, so a
    client that trusted it polled a settled job forever."""
    out = format_snapshot(
        snapshot(state="done", report=""), running_footer="Still running. Poll again."
    )
    assert "Still running" not in out
    assert out.endswith("\nREPORT\n(no report text)")


def test_a_failed_run_reports_the_error() -> None:
    out = format_snapshot(snapshot(state="failed", error="BoomError: x"))
    assert out.endswith("\nERROR  BoomError: x")


def test_a_running_snapshot_appends_the_callers_footer() -> None:
    out = format_snapshot(snapshot(), running_footer=FOOTER)
    assert out.endswith(f"\n{FOOTER}")


def test_a_running_snapshot_without_a_footer_gives_no_polling_instructions() -> None:
    """The instructions used to be hardcoded here, naming an MCP tool by hand —
    so a CLI run printed advice about a tool it does not have."""
    out = format_snapshot(snapshot(trail=[("commander", "plan: fan out")]))
    assert "check_task" not in out
    assert "poll" not in out.lower()
    assert out.endswith("  plan: fan out")


@pytest.mark.parametrize(
    "finished",
    [{"state": "done", "report": "THE REPORT"}, {"state": "failed", "error": "boom"}],
    ids=["done", "failed"],
)
def test_a_settled_snapshot_never_asks_the_caller_to_poll_again(
    finished: dict[str, Any],
) -> None:
    out = format_snapshot(snapshot(**finished), running_footer=FOOTER)
    assert FOOTER not in out


def test_usage_is_included_in_a_snapshot_that_carries_it() -> None:
    out = format_snapshot(snapshot(usage=usage_report()))
    assert "TOKENS" in out
    assert "critic" in out


def test_usage_rows_are_ranked_biggest_consumer_first() -> None:
    """The heading promises a ranking, so the formatter applies one.

    Fed in ascending order on purpose: trusting the producer's ordering meant
    any other source of a per_agent mapping silently lost the ranking.
    """
    ascending = usage_report()["per_agent"]
    unsorted = {"network": ascending["network"], "critic": ascending["critic"]}
    rows = [
        line
        for line in format_usage(usage_report(per_agent=unsorted)).splitlines()
        if "total" in line
    ]
    assert [line.split()[0] for line in rows] == ["critic", "network", "TOTAL"]


def test_usage_reports_the_split_and_the_call_count_per_agent() -> None:
    line = next(
        line for line in format_usage(usage_report()).splitlines() if "network" in line
    )
    assert "1,000 total" in line
    assert "900 in + " in line and "100 out" in line
    assert "over  2 calls" in line


@pytest.mark.parametrize(
    ("field", "expected"),
    [("reasoning", "(2,500 reasoning)"), ("cached", "(2,500 cached)")],
)
def test_usage_shows_a_detail_suffix_only_when_that_detail_is_non_zero(
    field: str, expected: str
) -> None:
    """Zeroed suffixes on every row hide the rows that really did use them."""
    assert expected not in format_usage(usage_report())
    rows = usage_report()["per_agent"]
    rows["critic"][field] = 2_500
    out = format_usage(usage_report(per_agent=rows))
    assert expected in out
    assert out.count(expected) == 1


def test_usage_ends_with_a_total_over_every_model_call() -> None:
    """Padded to the agent column so the totals line up under the rows."""
    lines = format_usage(usage_report()).splitlines()
    assert lines[-1] == "  TOTAL    129,000 total  over 6 model calls"
    rows = [line for line in lines if " total" in line]
    assert len({line.index(" total") for line in rows}) == 1


def test_usage_mentions_langsmith_only_when_tracing_is_configured() -> None:
    assert "LangSmith" not in format_usage(usage_report())
    assert "LangSmith" in format_usage(usage_report(langsmith=True))


def test_usage_is_empty_when_no_model_call_has_been_accounted_for() -> None:
    """Callers concatenate this, so an empty report must add no blank heading."""
    assert format_usage({"per_agent": {}, "total_tokens": 0, "model_calls": 0}) == ""


def test_snapshot_line_carries_the_identity_state_and_request_of_one_job() -> None:
    line = format_snapshot_line(snapshot())
    assert line.startswith("j1  stub")
    assert "running" in line
    assert "12.5s" in line
    assert "why does payments return 502" in line


def test_snapshot_line_clips_a_long_request_to_keep_a_listing_scannable() -> None:
    line = format_snapshot_line(snapshot(request="x" * 200))
    assert "x" * 60 in line
    assert "x" * 61 not in line


@pytest.mark.parametrize(
    ("roster", "expected"),
    [("", ""), ("  network  routing", "\nstub roster:\n  network  routing")],
    ids=["no-members", "members"],
)
def test_roster_block_is_omitted_entirely_for_a_team_without_members(
    roster: str, expected: str
) -> None:
    assert format_roster("stub", roster) == expected
