"""Stream interpretation: attribution, content shapes, report filing.

Every case here is a bug that actually reached a user, so each test names the
symptom it prevents rather than the function it exercises.
"""

from __future__ import annotations

from langchain_core.messages import AIMessage, ToolMessage

from swarmr.core.events import EventKind, EventReader


def dispatch(subagent: str, call_id: str) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": "task",
                "id": call_id,
                "args": {"subagent_type": subagent, "description": "look into it"},
            }
        ],
    )


def kinds(reader: EventReader, namespace: tuple[str, ...], payload: dict) -> list[str]:
    return [event.kind.value for event in reader.read(namespace, payload)]


def test_verdict_survives_content_blocks() -> None:
    """A verdict returned as content blocks was rendered as Python repr."""
    reader = EventReader()
    list(reader.read((), {"m": {"messages": [dispatch("network", "c1")]}}))
    events = list(
        reader.read(
            (),
            {
                "t": {
                    "messages": [
                        ToolMessage(
                            content=[{"type": "text", "text": "VERDICT: implicated"}],
                            tool_call_id="c1",
                        )
                    ]
                }
            },
        )
    )
    verdicts = [e for e in events if e.kind is EventKind.VERDICT]
    assert verdicts and verdicts[0].text == "VERDICT: implicated"
    assert verdicts[0].who == "network"


def test_audit_payload_only_for_declared_agents() -> None:
    """An adjudicator's input is echoed; ordinary dispatches are not."""
    reader = EventReader(audit_agents=("critic",))
    assert "audit_input" not in kinds(
        reader, (), {"m": {"messages": [dispatch("network", "c1")]}}
    )
    assert "audit_input" in kinds(
        reader, (), {"m": {"messages": [dispatch("critic", "c2")]}}
    )


def test_root_events_are_labelled_root() -> None:
    reader = EventReader()
    events = list(reader.read((), {"m": {"messages": [dispatch("network", "c1")]}}))
    assert events[0].stream == "root"
    assert events[0].root is True


def test_subgraph_events_carry_a_stream_tag() -> None:
    """Concurrent subagents interleave; without a tag they are indistinguishable."""
    reader = EventReader()
    call = AIMessage(
        content="",
        tool_calls=[{"name": "k_get", "id": "t1", "args": {"kind": "pod"}}],
    )
    events = list(reader.read(("tools:abcd1234",), {"t": {"messages": [call]}}))
    assert events[0].stream == "abcd"
    assert events[0].root is False


def test_filed_report_is_captured_and_receipt_suppressed() -> None:
    """The filing is the deliverable; its receipt carries no information."""
    reader = EventReader(
        report_tool="file_report",
        render_report=lambda args: f"ROOT CAUSE\n{args['root_cause']}",
    )
    filing = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "file_report",
                "id": "r1",
                "args": {"root_cause": "targetPort 8081 vs 80"},
            }
        ],
    )
    events = list(reader.read((), {"m": {"messages": [filing]}}))
    assert [e.kind for e in events] == [EventKind.FILED_REPORT]
    assert "targetPort 8081" in events[0].text

    receipt = ToolMessage(content="Report filed.", tool_call_id="r1")
    assert kinds(reader, (), {"t": {"messages": [receipt]}}) == []


def test_ordinary_tool_results_still_surface() -> None:
    """Suppressing filing receipts must not suppress real results."""
    reader = EventReader(report_tool="file_report")
    call = AIMessage(
        content="", tool_calls=[{"name": "k_get", "id": "t9", "args": {"kind": "pod"}}]
    )
    assert kinds(reader, (), {"m": {"messages": [call]}}) == ["call"]
    result = ToolMessage(content='{"kind":"Pod","count":2}', tool_call_id="t9")
    assert kinds(reader, (), {"t": {"messages": [result]}}) == ["result"]


def test_first_dispatch_shows_the_briefing_the_subagent_receives() -> None:
    """The harness replaces round-one briefings, so the display must match."""
    reader = EventReader(audit_agents=("critic",), request="pods will not start in demo")
    verbose = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "task",
                "id": "c1",
                "args": {
                    "subagent_type": "workload",
                    "description": "Check exit codes, restart reasons, events, "
                    "image pull issues, and report exact pod names.",
                },
            }
        ],
    )
    events = list(reader.read((), {"m": {"messages": [verbose]}}))
    assert events[0].text == "pods will not start in demo"


def test_later_dispatches_keep_their_targeted_question() -> None:
    """Round two is specific on purpose: it re-tests a claim that broke."""
    reader = EventReader(audit_agents=("critic",), request="pods will not start in demo")
    list(reader.read((), {"m": {"messages": [dispatch("workload", "c1")]}}))
    followup = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "task",
                "id": "c2",
                "args": {
                    "subagent_type": "workload",
                    "description": "Confirm whether container web ever started.",
                },
            }
        ],
    )
    events = list(reader.read((), {"m": {"messages": [followup]}}))
    assert events[0].text == "Confirm whether container web ever started."


def test_adjudicator_briefing_is_never_replaced() -> None:
    """Its payload is a hypothesis, which is exactly what it must receive."""
    reader = EventReader(audit_agents=("critic",), request="pods will not start in demo")
    events = list(reader.read((), {"m": {"messages": [dispatch("critic", "c9")]}}))
    assert events[0].text == "look into it"


def test_subagent_prose_is_not_echoed_as_a_report() -> None:
    """Only root-level prose is a candidate report; subagent prose is its verdict."""
    reader = EventReader()
    chatter = AIMessage(content="thinking out loud")
    assert kinds(reader, ("tools:abcd",), {"m": {"messages": [chatter]}}) == []
    assert kinds(reader, (), {"m": {"messages": [chatter]}}) == ["report"]


def test_prose_after_filing_is_suppressed() -> None:
    """The filing is the deliverable; trailing prose is noise.

    A live run against Kimi's coding endpoint (which proxies to Anthropic)
    returned a literal "(Empty response: {...})" placeholder — Anthropic's
    thinking signature included — as assistant text after the report was filed.
    """
    reader = EventReader(report_tool="file_incident_report", request="r")
    filing = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "file_incident_report",
                "args": {"root_cause": "r"},
                "id": "c1",
            }
        ],
    )
    # The receipt must sit between them: it is the real sequence, and it
    # discards the filing's call id — so pending-call state cannot stand in for
    # "the report has been filed".
    receipt = ToolMessage(content="Report filed. Stop here.", tool_call_id="c1")
    trailing = AIMessage(content="(Empty response: {'content': [...], 'model': 'x'})")
    kinds = [e.kind for e in reader.read((), {"a": {"messages": [filing]}})]
    assert EventKind.FILED_REPORT in kinds
    assert list(reader.read((), {"a": {"messages": [receipt]}})) == []
    assert list(reader.read((), {"a": {"messages": [trailing]}})) == []


def test_prose_before_filing_still_reports() -> None:
    reader = EventReader(report_tool="file_incident_report", request="r")
    early = AIMessage(content="I am opening a parallel investigation")
    assert [e.kind for e in reader.read((), {"a": {"messages": [early]}})] == [
        EventKind.REPORT
    ]
