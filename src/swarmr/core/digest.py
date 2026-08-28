"""Shape-only summary of a tool result, for teams that supply no digester.

Its own module because both the terminal renderer and the job store need it:
having it live in the renderer meant the job store — which never prints
anything — imported the presentation layer to get a default.

It reports shape and nothing else: how many items, which keys, how many lines.
Interpreting a payload requires knowing the domain, and `core` does not. A team
that wants better supplies `Team.digest`.
"""

from __future__ import annotations

import json

from swarmr.core.text import clip

__all__ = ["generic_digest"]


def generic_digest(text: str) -> str:
    """Domain-agnostic one-line summary of a tool result."""
    stripped = text.strip()
    if not stripped:
        return "empty"
    if stripped.startswith(("{", "[")):
        try:
            data = json.loads(stripped)
        except json.JSONDecodeError:
            return f"{len(text)}B truncated json"
        if isinstance(data, list):
            return f"{len(data)} items"
        return f"{len(data)} fields [{', '.join(list(data)[:4])}]"
    lines = [line for line in stripped.splitlines() if line.strip()]
    return f"{len(lines)} lines | {clip(lines[-1] if lines else '', 70)}"
