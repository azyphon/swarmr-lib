"""Job state: incremental trail, atomic settlement, milestone semantics.

Both the delta trail and the atomic settle fixed live defects: polls resent the
whole trail so new lines fell past the client's display cutoff, and a poll could
observe `state=done` before the report was attached.
"""

from __future__ import annotations

from typing import Any

from swarmr.core.events import Event, EventKind
from swarmr.core.jobs import Job, JobState, JobStore


def call(text: str, stream: str = "a1b2") -> Event:
    return Event(EventKind.CALL, "k_get", text, False, stream)


def verdict(who: str, text: str) -> Event:
    return Event(EventKind.VERDICT, who, text, True, "root")


def test_trail_is_strictly_incremental() -> None:
    """Filtering by milestone resent lines while one subagent worked for minutes."""
    job = Job(id="j1", team="t", request="r")
    job.record(call("k_get(a)"))
    job.record(call("k_get(b)"))
    first = job.snapshot()
    assert len(first["trail"]) == 2

    # Nothing new: a poll at the same cursor must return no trail at all.
    assert "trail" not in job.snapshot(since_cursor=first["trail_cursor"])

    job.record(call("k_get(c)"))
    second = job.snapshot(since_cursor=first["trail_cursor"])
    assert second["trail"] == [("a1b2", "k_get(c)")]
    assert second["trail_cursor"] > first["trail_cursor"]


def test_milestones_only_advance_on_delegation_and_verdicts() -> None:
    """Long-polls wake on milestones, so an ordinary tool call must not raise one."""
    job = Job(id="j2", team="t", request="r")
    job.record(call("k_get(a)"))
    assert job.milestone == 0
    job.record(Event(EventKind.DISPATCH, "network", "go", True, "root"))
    assert job.milestone == 1
    job.record(verdict("network", "VERDICT: implicated"))
    assert job.milestone == 2


def test_verdict_headline_skips_blank_lines_and_markdown() -> None:
    """A verdict opening with blank lines showed as "(no verdict text)"."""
    job = Job(id="j3", team="t", request="r")
    job.record(verdict("critic", "\n\n**RULING: confirmed**\nbecause..."))
    assert job.snapshot()["verdicts"]["critic"] == "RULING: confirmed"


def test_settle_is_atomic() -> None:
    """A poll must never see state=done with the report still unset."""
    job = Job(id="j4", team="t", request="r")
    job.settle("REPORT BODY", "3 nodes")
    snap = job.snapshot()
    assert snap["state"] == "done"
    assert snap["report"] == "REPORT BODY"
    assert snap["target"] == "3 nodes"
    assert job.finished is not None
    assert job.milestone == 1, "settling must wake a waiting long-poll"


def test_fail_records_the_error_and_clears_workers() -> None:
    job = Job(id="j5", team="t", request="r")
    job.record(Event(EventKind.DISPATCH, "network", "go", True, "root"))
    job.fail("BoomError: x")
    snap = job.snapshot()
    assert snap["state"] == "failed"
    assert snap["error"] == "BoomError: x"
    assert "waiting_on" not in snap


def test_orchestrator_label_comes_from_the_team() -> None:
    """`core` must not assume a role name such as "commander" exists."""
    job = Job(id="j6", team="t", request="r", orchestrator="foreman")
    job.record(Event(EventKind.PLAN, "", "survey", True, "root"))
    snap = job.snapshot()
    assert snap["trail"] == [("foreman", "plan: survey")]
    assert snap["waiting_on"] == ["foreman"]


def test_digest_comes_from_the_team() -> None:
    """Summarising a result is domain knowledge, so the team supplies it."""
    job = Job(
        id="j7", team="t", request="r", digest=lambda text: f"summarised {len(text)}B"
    )
    job.record(Event(EventKind.RESULT, "k_get", "x" * 10, False, "a1b2"))
    assert job.snapshot()["trail"] == [("a1b2", "<- k_get: summarised 10B")]


def test_trail_records_the_author_separately_from_the_text() -> None:
    """So a reader can group by who acted instead of parsing an inline tag."""
    job = Job(id="j8", team="t", request="r", orchestrator="commander")
    job.record(Event(EventKind.DISPATCH, "network", "look at routing", True, "root"))
    job.record(Event(EventKind.CALL, "k_get", "k_get(kind=svc)", False, "network"))
    job.record(Event(EventKind.VERDICT, "network", "VERDICT: implicated", True, "root"))
    assert job.snapshot()["trail"] == [
        ("commander", "-> network: look at routing"),
        ("network", "k_get(kind=svc)"),
        ("network reports", "VERDICT: implicated"),
    ]


def test_store_captures_a_failing_run_instead_of_crashing(settled: Any) -> None:
    def work(job: Job) -> tuple[str, str]:
        raise RuntimeError("nope")

    job = settled(JobStore().start("t", "r", work))
    assert job.state is JobState.FAILED
    assert job.error is not None and "nope" in job.error


def test_store_publishes_a_successful_run(settled: Any) -> None:
    job = settled(JobStore().start("t", "r", lambda _job: ("THE REPORT", "the target")))
    snap = job.snapshot()
    assert snap["state"] == "done"
    assert snap["report"] == "THE REPORT"


def test_store_evicts_only_settled_jobs(settled: Any) -> None:
    store = JobStore(retain=3)
    for index in range(5):
        settled(store.start("t", f"r{index}", lambda _job: ("done", "target")))
    assert len(store.list()) <= 3
