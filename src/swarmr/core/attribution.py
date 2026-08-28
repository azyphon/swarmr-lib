"""Resolving a LangGraph stream id to the subagent that owns it.

The update stream identifies a subgraph only as `tools:<uuid>`, so subagents
running concurrently are indistinguishable in the trail. Deep Agents does record
the subagent's name, as graph metadata `lc_agent_name`, but that metadata never
reaches `stream_mode="updates"`.

The bridge is the agent's own runtime config: a model call runs *inside* the
subagent's graph, so `langgraph.config.get_config()` yields the checkpoint
namespace. Binding that namespace to the name the team already knows turns every
later `[a1b2]` tag into the subagent's own name. The middleware that does the
binding lives in `core.middleware`; this module is only the map, so it stays
importable without pulling the agent framework in.

Per run, never global. The map used to be module state cleared at the start of
every run, which meant a second run starting while the first was still going
wiped the first one's names mid-flight and then wrote into the same namespace.
The MCP surface starts runs on demand, so that was reachable. A run now owns its
own `Attribution` and two runs cannot see each other's.

Best-effort by design: if a future LangGraph release stops exposing the
namespace, `label` returns the raw tag and the trail is merely less readable.
"""

from __future__ import annotations

import threading

__all__ = ["Attribution", "current_namespace", "tag_of"]


def tag_of(namespace: str) -> str:
    """Short, stable tag for a checkpoint namespace or stream id."""
    return namespace.split(":")[-1][:4] if namespace else ""


def current_namespace() -> str:
    """The running graph's checkpoint namespace, or "" outside a graph.

    LangGraph is imported inside the call so this module costs nothing to
    import, and so a missing or changed API degrades to "no attribution"
    instead of breaking a run.
    """
    try:
        from langgraph.config import get_config

        configurable = get_config().get("configurable") or {}
    except Exception:
        return ""
    return str(configurable.get("checkpoint_ns") or "")


class Attribution:
    """One run's map of stream tag -> subagent name.

    Thread-safe: subagents run concurrently on their own threads inside one
    graph, and the reader consuming the stream is a third.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._names: dict[str, str] = {}

    def note(self, agent_name: str, namespace: str | None = None) -> None:
        """Bind every segment of the current namespace to `agent_name`.

        A tool's `checkpoint_ns` is the full path, e.g.
            "tools:<task-node>|tools:<subagent-graph>"
        while `stream_mode="updates"` reports only the outer segment. Every
        segment is registered so the lookup matches whichever one the stream
        reports; registering just the last one silently never matches.
        """
        path = current_namespace() if namespace is None else namespace
        if not path:
            return
        with self._lock:
            for segment in path.split("|"):
                if tag := tag_of(segment):
                    self._names.setdefault(tag, agent_name)

    def resolve(self, tag: str) -> str | None:
        """The subagent owning this tag, if it has run anything yet."""
        with self._lock:
            return self._names.get(tag)

    def label(self, namespace: tuple[str, ...]) -> str:
        """Display label for a stream: the subagent's name, else its raw tag.

        The name only becomes available once that subagent has made one model
        call, so early lines may carry the tag. That is honest: guessing an
        owner from dispatch order breaks as soon as two subagents run at once.
        """
        if not namespace:
            return "root"
        tag = tag_of(namespace[-1])
        return self.resolve(tag) or tag
