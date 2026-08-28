"""Background job store for long-running team runs.

An investigation takes minutes; MCP is request/response and every client
enforces its own timeout. So the MCP surface is a job API — start returns an id
immediately, check polls — rather than one blocking call that dies at the
client's timeout with the work thrown away.

A poll returns the delegation trail as well as the state, because a job with no
progress signal is indistinguishable from a hung one.
"""

from __future__ import annotations

import threading
import time
import uuid
from collections import Counter, deque
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from swarmr.core.digest import generic_digest
from swarmr.core.events import Event, EventKind
from swarmr.core.team import TeamError

__all__ = ["Job", "JobState", "JobStore"]

# Enough trail to see the shape of an investigation without turning a poll into
# a transcript dump. Tool calls are the bulk; dispatches and verdicts are few.
_TRAIL_LIMIT = 120
_VERDICT_PREVIEW = 400


def _headline(text: str) -> str:
    """First line that actually says something.

    A verdict can open with a blank line or a markdown heading, and taking
    line zero blindly yields an empty headline in the summary.
    """
    for line in (text or "").splitlines():
        stripped = line.strip().strip("#*_` ").strip()
        if stripped:
            return stripped[:120]
    return "(no verdict text)"


class JobState(StrEnum):
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass(slots=True)
class Job:
    """One team run, observable while it happens."""

    id: str
    team: str
    request: str
    state: JobState = JobState.RUNNING
    started: float = field(default_factory=time.monotonic)
    finished: float | None = None
    result: str | None = None
    error: str | None = None
    target: str = ""
    # (sequence, author, line). The sequence is strictly increasing for the life
    # of the job, which is what lets a poller ask for "everything after cursor
    # N". Author is kept separate from the text so a reader can group the trail
    # by who acted, rather than reading an inline tag on every line.
    trail: deque[tuple[int, str, str]] = field(
        default_factory=lambda: deque(maxlen=_TRAIL_LIMIT)
    )
    trail_seq: int = 0
    usage: dict[str, Any] | None = None
    # Supplied by the team: what to call root activity, and how to summarise its
    # tool results. `core` must not know either.
    orchestrator: str = "orchestrator"
    digest: Callable[[str], str] = generic_digest
    tool_calls: Counter[str] = field(default_factory=Counter)
    verdicts: dict[str, str] = field(default_factory=dict)
    active: set[str] = field(default_factory=set)
    # Bumped only on milestones: a dispatch, a verdict, a plan, or the run
    # settling. Long-pollers wake on this rather than on every tool call, so a
    # client spends a handful of polls per run instead of one per read.
    milestone: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @property
    def elapsed(self) -> float:
        return (self.finished or time.monotonic()) - self.started

    def record(self, event: Event) -> None:
        """Fold one run event into the observable trail.

        Called from the worker thread while the MCP loop may be reading, so
        every mutation takes the lock.
        """
        with self._lock:
            match event.kind:
                case EventKind.PLAN:
                    self._append(self.orchestrator, f"plan: {event.text}")
                    self.milestone += 1
                case EventKind.DISPATCH:
                    self.active.add(event.who)
                    self._append(self.orchestrator, f"-> {event.who}: {event.text}")
                    self.milestone += 1
                case EventKind.CALL:
                    self.tool_calls[event.who] += 1
                    self._append(self._author(event), event.text)
                case EventKind.RESULT:
                    label = f"{event.who}: " if event.who else ""
                    self._append(
                        self._author(event), f"<- {label}{self.digest(event.text)}"
                    )
                case EventKind.VERDICT:
                    self.active.discard(event.who)
                    self.verdicts[event.who] = event.text[:_VERDICT_PREVIEW]
                    self._append(f"{event.who} reports", _headline(event.text))
                    self.milestone += 1
                case EventKind.FILED_REPORT:
                    self._append(self.orchestrator, "filed the report")
                    self.milestone += 1
                case EventKind.AUDIT_INPUT | EventKind.REPORT:
                    # AUDIT_INPUT is the adjudicator's raw input and REPORT is
                    # the final answer; both are returned in full elsewhere.
                    pass

    def _append(self, author: str, line: str) -> None:
        """Record a trail line under its own sequence number.

        A per-line sequence, not the milestone: a milestone can stall for
        minutes while one subagent works, so filtering by milestone would
        resend the same lines on every timeout. The cursor is what makes a poll strictly
        incremental. Caller already holds the lock.
        """
        self.trail_seq += 1
        self.trail.append((self.trail_seq, author, line))

    def _author(self, event: Event) -> str:
        """Who acted. Subagents name themselves once their first model call runs."""
        return self.orchestrator if event.root else (event.stream or "delegated")

    def set_target(self, banner: str) -> None:
        """Record what is being investigated, atomically.

        A method rather than a bare attribute write from the worker thread:
        every other mutation on this class takes the lock, and `settle` reads
        `target` to decide whether to fill it, so a write that skips the lock
        skips the discipline the rest of the class depends on.
        """
        with self._lock:
            self.target = banner

    def settle(self, report: str, banner: str) -> None:
        """Mark the run finished, atomically.

        State, result, target and finish time are written together under the
        lock: a poll must never observe state=done with the report still unset.
        The milestone bump wakes any long-poller immediately.
        """
        with self._lock:
            self.result = report
            self.target = self.target or banner
            self.finished = time.monotonic()
            self.state = JobState.DONE
            self.active.clear()
            self.milestone += 1

    def fail(self, error: str) -> None:
        """Mark the run failed, atomically."""
        with self._lock:
            self.error = error
            self.finished = time.monotonic()
            self.state = JobState.FAILED
            self.active.clear()
            self.milestone += 1

    def snapshot(
        self, trail: bool = True, since_cursor: int | None = None
    ) -> dict[str, Any]:
        """Capture a consistent view of the job.

        Taken under the lock and containing only copies, so a caller may format
        or serialise it while the worker thread keeps recording. Returning live
        containers here would let a poll iterate a mutating dict.
        """
        with self._lock:
            payload: dict[str, Any] = {
                "job": self.id,
                "team": self.team,
                "request": self.request,
                "state": str(self.state),
                "elapsed_seconds": round(self.elapsed, 1),
                "milestone": self.milestone,
            }
            if self.target:
                payload["target"] = self.target
            if self.tool_calls:
                payload["tool_calls"] = dict(self.tool_calls.most_common())
            if self.verdicts:
                payload["verdicts"] = {
                    who: _headline(text) for who, text in self.verdicts.items()
                }
            if self.state is JobState.RUNNING:
                payload["waiting_on"] = sorted(self.active) or [self.orchestrator]
            payload["trail_cursor"] = self.trail_seq
            if self.usage:
                payload["usage"] = self.usage
            if trail and self.trail:
                if since_cursor is None:
                    rows = [(author, line) for _, author, line in self.trail]
                    payload["trail_is_delta"] = False
                else:
                    rows = [
                        (author, line)
                        for seq, author, line in self.trail
                        if seq > since_cursor
                    ]
                    payload["trail_is_delta"] = True
                if rows:
                    payload["trail"] = rows
                payload["trail_total"] = self.trail_seq
            if self.state is JobState.DONE:
                payload["report"] = self.result
            elif self.state is JobState.FAILED:
                payload["error"] = self.error
            return payload


class JobStore:
    """Thread-backed job registry.

    Threads, not asyncio: the agent graph and its clients are synchronous, so a
    thread per run is the honest model and keeps the MCP event loop free to
    answer polls while an investigation is in flight.
    """

    def __init__(self, retain: int = 32) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._retain = retain

    def start(
        self,
        team: str,
        request: str,
        work: Callable[[Job], tuple[str, str]],
        orchestrator: str = "orchestrator",
        digest: Callable[[str], str] | None = None,
    ) -> Job:
        """Run `work` in the background.

        `work` receives the Job so it can record progress, and returns
        (report, banner). It may raise: the exception is captured on the job
        rather than killing the server.
        """
        job = Job(
            id=uuid.uuid4().hex[:12],
            team=team,
            request=request,
            orchestrator=orchestrator,
            digest=digest or generic_digest,
        )
        with self._lock:
            self._evict()
            self._jobs[job.id] = job

        def runner() -> None:
            try:
                report, banner = work(job)
            except TeamError as exc:
                # The team says this is the operator's to fix, so the reason is
                # the sentence. A class name in front would only make an MCP
                # client read it as a crash.
                job.fail(str(exc))
            except Exception as exc:
                job.fail(f"{type(exc).__name__}: {exc}")
            else:
                job.settle(report, banner)

        threading.Thread(target=runner, name=f"team-{team}-{job.id}", daemon=True).start()
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list(self) -> list[Job]:
        with self._lock:
            return sorted(self._jobs.values(), key=lambda j: j.started, reverse=True)

    def _evict(self) -> None:
        """Drop the oldest settled jobs once the store is full."""
        if len(self._jobs) < self._retain:
            return
        settled = sorted(
            (j for j in self._jobs.values() if j.state is not JobState.RUNNING),
            key=lambda j: j.finished or 0.0,
        )
        for job in settled[: max(1, len(self._jobs) - self._retain + 1)]:
            self._jobs.pop(job.id, None)
