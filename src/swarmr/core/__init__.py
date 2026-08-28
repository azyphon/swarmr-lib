"""Shared, domain-free machinery every team builds on.

Nothing here may know about Kubernetes, Terraform or any other domain. That
constraint is what makes a team package deletable: teams depend on `core`,
never on each other, and never the other way round.

Dependency direction inside `core` runs one way: contract (`team`, `harness`) <-
interpretation (`events`, `briefing`, `attribution`) <- presentation (`render`,
`report`) <- framework adapters (`middleware`, `model`, `usage`), with `text` and
`digest` at the bottom, depended on by anything. The job store deliberately
depends on `digest` rather than on `render`: it records, it never prints.

Re-exports are resolved on attribute access, not at import. A package
initializer runs before any of its submodules, so an eager list here meant that
`import swarmr.core.text` — thirty lines of stdlib string handling —
pulled in the model SDK and the agent framework. `from swarmr.core
import Renderer` still works, and loads exactly what it names.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from swarmr.core.digest import generic_digest as generic_digest
    from swarmr.core.events import Event as Event
    from swarmr.core.events import EventKind as EventKind
    from swarmr.core.events import EventReader as EventReader
    from swarmr.core.jobs import Job as Job
    from swarmr.core.jobs import JobState as JobState
    from swarmr.core.jobs import JobStore as JobStore
    from swarmr.core.middleware import AnnounceName as AnnounceName
    from swarmr.core.middleware import FirstRoundBriefing as FirstRoundBriefing
    from swarmr.core.model import build_model as build_model
    from swarmr.core.model import load_env as load_env
    from swarmr.core.render import Renderer as Renderer
    from swarmr.core.runner import Observer as Observer
    from swarmr.core.runner import run as run
    from swarmr.core.runner import run_streamed as run_streamed
    from swarmr.core.team import Lazy as Lazy
    from swarmr.core.team import Member as Member
    from swarmr.core.team import RunContext as RunContext
    from swarmr.core.team import Team as Team
    from swarmr.core.team import TeamBuild as TeamBuild
    from swarmr.core.team import TeamBuilder as TeamBuilder
    from swarmr.core.team import TeamError as TeamError
    from swarmr.core.text import clip as clip
    from swarmr.core.text import content_text as content_text
    from swarmr.core.text import wrap as wrap

__all__ = [
    "AnnounceName",
    "Event",
    "EventKind",
    "EventReader",
    "FirstRoundBriefing",
    "Job",
    "JobState",
    "JobStore",
    "Lazy",
    "Member",
    "Observer",
    "Renderer",
    "RunContext",
    "Team",
    "TeamBuild",
    "TeamBuilder",
    "TeamError",
    "build_model",
    "clip",
    "content_text",
    "generic_digest",
    "load_env",
    "run",
    "run_streamed",
    "wrap",
]

# public name -> defining submodule
_EXPORTS: dict[str, str] = {
    "AnnounceName": "middleware",
    "Event": "events",
    "EventKind": "events",
    "EventReader": "events",
    "FirstRoundBriefing": "middleware",
    "Job": "jobs",
    "JobState": "jobs",
    "JobStore": "jobs",
    "Lazy": "team",
    "Member": "team",
    "Observer": "runner",
    "Renderer": "render",
    "RunContext": "team",
    "Team": "team",
    "TeamBuild": "team",
    "TeamBuilder": "team",
    "TeamError": "team",
    "build_model": "model",
    "clip": "text",
    "content_text": "text",
    "generic_digest": "digest",
    "load_env": "model",
    "run": "runner",
    "run_streamed": "runner",
    "wrap": "text",
}


def __getattr__(name: str) -> Any:
    """Load a re-export on first use (PEP 562)."""
    try:
        module = _EXPORTS[name]
    except KeyError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None
    from importlib import import_module

    return getattr(import_module(f"{__name__}.{module}"), name)


def __dir__() -> list[str]:
    return list(__all__)
