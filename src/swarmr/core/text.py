"""Text helpers shared by the event reader, the renderer and the runner.

Small on purpose. `content_text` in particular was duplicated in two modules and
is a genuine bug surface: a provider may return a list of content blocks instead
of a string, and every reader that treats that as "no text" silently drops real
output. One definition, one place to fix.

It lives in its own module because `stream` imports from `events`, so the shared
helpers cannot live in either without creating a cycle.
"""

from __future__ import annotations

import shutil
import textwrap
from typing import Any

__all__ = ["clip", "content_text", "flatten", "wrap"]

MAX_WIDTH = 100
MIN_WIDTH = 60


def flatten(value: Any) -> str:
    """Collapse whitespace to a single line, without shortening it."""
    return " ".join(str(value).split())


def clip(value: Any, limit: int) -> str:
    """Shorten to `limit`, breaking at a word boundary rather than mid-word.

    Used only for payloads that are genuinely unbounded, such as a file body.
    Sentences a reader is meant to understand are never clipped: a half sentence
    ending in an ellipsis is worse than a wrapped one.
    """
    text = flatten(value)
    if len(text) <= limit:
        return text
    head = text[:limit].rsplit(" ", 1)[0]
    return f"{head or text[:limit]}…"


def width() -> int:
    """Usable line width for wrapped output."""
    columns = shutil.get_terminal_size(fallback=(MAX_WIDTH, 24)).columns
    return max(MIN_WIDTH, min(MAX_WIDTH, columns - 2))


def wrap(text: str, indent: str = "  ", subsequent: str | None = None) -> str:
    """Wrap prose to the terminal, preserving existing line breaks.

    Blank lines are kept, because a report's paragraph structure is part of its
    readability.
    """
    limit = width()
    lead = subsequent if subsequent is not None else indent
    out: list[str] = []
    for line in text.splitlines():
        stripped = line.rstrip()
        if not stripped:
            out.append("")
            continue
        out.extend(
            textwrap.wrap(
                stripped,
                width=limit,
                initial_indent=indent,
                subsequent_indent=lead,
                break_long_words=False,
                break_on_hyphens=False,
            )
            or [indent]
        )
    return "\n".join(out)


def content_text(content: Any) -> str:
    """Flatten message content to text, whatever shape the provider used.

    Handles a plain string and a list of content blocks. Anything else yields an
    empty string, which callers treat as "this message carried no prose".
    """
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and block.get("type") == "text":
            parts.append(str(block.get("text", "")))
    return "\n".join(part for part in parts if part).strip()
