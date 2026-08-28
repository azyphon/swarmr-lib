"""Fixtures for every suite, wherever it lives.

Slice tests live inside the package they cover (`src/swarmr/core/tests`) and the
tests of the composed whole live in `tests/`. A conftest only applies to its own
directory downwards, so the shared fixtures belong at the root — the one
directory that is an ancestor of both.

The stubs themselves are library code in `swarmr.core.testing`: a team in its
own distribution tests against the same `Team` and `Job` stand-ins, and cannot
reach into this file. Only the pytest wrapping lives here.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from importlib.metadata import PackageNotFoundError, distribution

import pytest

from swarmr.core.jobs import Job, JobState
from swarmr.core.testing import JobFactory, TeamFactory


def pytest_sessionstart() -> None:
    """Refuse to run against a source tree that was never installed.

    Discovery reads the `swarmr.teams` entry-point group from distribution
    metadata. Put `src` on `PYTHONPATH` without installing and every import
    works while `entry_points` sees nothing, so failures land on assertions
    about team names and read like a broken registry rather than a missing
    install. There is deliberately no source-tree fallback: a second discovery
    path would also hide a genuinely broken install, and editing an entry point
    requires a reinstall either way.

    Core ships no team, so the check is that *core itself* is installed, not
    that the group is populated — an empty group is core's normal state.
    """
    try:
        distribution("swarmr")
    except PackageNotFoundError:
        raise pytest.UsageError(
            "swarmr is not installed: install the project before testing, e.g. "
            '.venv/bin/pip install -e ".[dev]". Team discovery reads '
            "distribution metadata, so an uninstalled source tree has no "
            "metadata to read and the discovery tests cannot pass."
        ) from None


@pytest.fixture
def stub_team() -> TeamFactory:
    """Factory for a `Team` whose graph replays caller-supplied chunks."""
    return TeamFactory()


@pytest.fixture
def job() -> JobFactory:
    """Factory for a `Job` to record events into."""
    return JobFactory()


@pytest.fixture
def settled() -> Callable[..., Job]:
    """Wait for a job to leave RUNNING: `JobStore` settles it on its own thread."""

    def wait(target: Job, timeout: float = 3.0) -> Job:
        deadline = time.monotonic() + timeout
        while target.state is JobState.RUNNING and time.monotonic() < deadline:
            time.sleep(0.01)
        return target

    return wait
