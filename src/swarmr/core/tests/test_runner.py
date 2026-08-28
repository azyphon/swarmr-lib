"""Report extraction: the part that twice lost a converged investigation.

Once the caller received only the commander's opening plan; once it received
"the run produced no final report" while every verdict was in and the critic had
confirmed. Both came from inferring the report out of the update stream.
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from swarmr.core.runner import run

PLAN = AIMessage(content="**Plan:** dispatch the investigators")
FILING = AIMessage(
    content="",
    tool_calls=[
        {
            "name": "file_report",
            "id": "r1",
            "args": {"root_cause": "targetPort 8081 vs containerPort 80"},
        }
    ],
)
RECEIPT = ToolMessage(content="Report filed.", tool_call_id="r1")
PROSE = AIMessage(content="SYMPTOM\n502\nROOT CAUSE\nprose form")
BLOCKS = AIMessage(
    content=[{"type": "text", "text": "SYMPTOM\n502\nROOT CAUSE\nblock form"}]
)


def test_each_run_gets_its_own_attribution(stub_team: Any) -> None:
    """Two runs at once must not share a tag -> name map."""
    team = stub_team([((), "values", {"messages": [PROSE]})])
    run(team, "one")
    run(team, "two")
    seen = stub_team.runs
    assert seen[0].attribution is not seen[1].attribution


def test_filed_report_wins_over_prose(stub_team: Any) -> None:
    """The filing is deliberate; prose is optional narration."""
    team = stub_team(
        [
            ((), "updates", {"m": {"messages": [PLAN]}}),
            ((), "updates", {"m": {"messages": [FILING]}}),
            ((), "updates", {"t": {"messages": [RECEIPT]}}),
            ((), "updates", {"m": {"messages": [PROSE]}}),
            ((), "values", {"messages": [HumanMessage(content="502"), PROSE]}),
        ]
    )
    report, banner = run(team, "502")
    assert "targetPort 8081" in report
    assert banner == "the target"


def test_no_filing_falls_back_to_final_state_prose(stub_team: Any) -> None:
    """A team without a report tool still reports, from the finished state."""
    team = stub_team(
        [
            ((), "updates", {"m": {"messages": [PLAN]}}),
            ((), "updates", {"m": {"messages": [PROSE]}}),
            ((), "values", {"messages": [HumanMessage(content="502"), PLAN, PROSE]}),
        ]
    )
    report, _ = run(team, "502")
    assert "prose form" in report


def test_content_blocks_are_not_discarded(stub_team: Any) -> None:
    """A list-of-blocks final answer was treated as "no text" and dropped."""
    team = stub_team(
        [
            ((), "updates", {"m": {"messages": [PLAN]}}),
            ((), "values", {"messages": [HumanMessage(content="502"), PLAN, BLOCKS]}),
        ]
    )
    report, _ = run(team, "502")
    assert "block form" in report


def test_plan_is_never_mistaken_for_the_report(stub_team: Any) -> None:
    """The exact first failure: only the opening plan reached the caller."""
    team = stub_team(
        [
            ((), "updates", {"m": {"messages": [PLAN]}}),
            ((), "values", {"messages": [HumanMessage(content="502"), PLAN, BLOCKS]}),
        ]
    )
    report, _ = run(team, "502")
    assert not report.startswith("**Plan:**")


def test_converged_run_without_closing_prose_still_reports(stub_team: Any) -> None:
    """The second failure: verdicts in, critic confirmed, nothing returned."""
    team = stub_team(
        [
            ((), "updates", {"m": {"messages": [FILING]}}),
            ((), "updates", {"t": {"messages": [RECEIPT]}}),
            ((), "values", {"messages": [HumanMessage(content="502"), FILING]}),
        ]
    )
    report, _ = run(team, "502")
    assert "ROOT CAUSE" in report
    assert "no final report" not in report


def test_observer_sees_every_event(stub_team: Any) -> None:
    seen: list[str] = []
    team = stub_team(
        [
            ((), "updates", {"m": {"messages": [FILING]}}),
            ((), "values", {"messages": [FILING]}),
        ]
    )
    run(team, "502", observe=lambda event: seen.append(event.kind.value))
    assert seen == ["filed_report"]


def test_target_hook_fires_before_the_run(stub_team: Any) -> None:
    """Callers show what is being investigated while the run is still going."""
    banners: list[str] = []
    team = stub_team([((), "values", {"messages": [PROSE]})])
    run(team, "502", on_target=banners.append)
    assert banners == ["the target"]
