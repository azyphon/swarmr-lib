"""Terminal renderer for a running team.

Pure presentation: it consumes `Event`s from `core.events` and prints them. Knows
nothing about any domain — no role names, no payload shapes, and no idea what a
failed tool result looks like. Summarising a result and recognising a failure are
both delegated to the team, because only the team knows what its output means.

Style rules, so a long run stays readable:
  * One dim label per section, no rule characters and no per-line gutter.
  * Prose is wrapped to the terminal, never truncated mid-sentence.
  * Only unbounded payloads (a file body) are clipped, at a word boundary.
"""

from __future__ import annotations

from collections.abc import Callable

from swarmr.core.digest import generic_digest
from swarmr.core.events import Event, EventKind
from swarmr.core.text import clip, wrap

__all__ = ["Renderer"]

# Muted sage green (256-colour 108). Desaturated on purpose: chrome should sit
# behind the content, and a low-saturation mid-tone stays legible over a
# transparent terminal on both light and dark desktops, where a bright green
# glows and a dark grey disappears.
_LABEL = "\033[38;5;108m"
_RESET = "\033[0m"
_ARG_LIMIT = 120


def _never(_text: str) -> bool:
    """No team-supplied failure test: nothing is marked as an error.

    Better than guessing. The prefixes this used to match ("tool error", "no
    logs", "No ") were one team's tool vocabulary sitting in the shared layer,
    so every other team got either silence or a false positive.
    """
    return False


class Renderer:
    """Print events as they arrive, grouped by who produced them.

    Args:
        colour: Emit ANSI colour on section labels.
        orchestrator: Label for root-level activity, supplied by the team.
        digest: Team's tool-result summariser. Falls back to shape-only output.
        is_error: Team's failure test. Falls back to marking nothing.
    """

    def __init__(
        self,
        colour: bool = True,
        orchestrator: str = "orchestrator",
        digest: Callable[[str], str] | None = None,
        is_error: Callable[[str], bool] | None = None,
    ) -> None:
        self.colour = colour
        self.orchestrator = orchestrator
        self.digest = digest or generic_digest
        self.is_error = is_error or _never
        self._section: str | None = None

    def field(self, label: str, value: str) -> None:
        """A run-header line: dim label, plain value, no decoration."""
        tag = f"{_LABEL}{label:<8}{_RESET}" if self.colour else f"{label:<8}"
        print(f"{tag} {value}", flush=True)

    def note(self, text: str) -> None:
        """Print an already-formatted block, e.g. the closing usage table.

        Exists so the runner never writes to stdout itself: one layer owns the
        terminal, which is what makes a headless run silent by construction.
        """
        if text:
            print(text, flush=True)

    def show(self, event: Event) -> None:
        match event.kind:
            case EventKind.VERDICT:
                self._section_break(f"{event.who} reports")
                print(wrap(event.text), flush=True)
            case EventKind.FILED_REPORT:
                self._section_break("report")
                print(wrap(event.text), flush=True)
            case EventKind.REPORT:
                # Prose from the orchestrator mid-run is narration, not the
                # deliverable; only a filed report is that.
                self._section_break(self.orchestrator)
                print(wrap(event.text), flush=True)
            case EventKind.PLAN:
                self._section_break(self.orchestrator)
                print(wrap(f"plan: {event.text}"), flush=True)
            case EventKind.DISPATCH:
                self._section_break(self.orchestrator)
                print(wrap(f"→ {event.who}: {event.text}", subsequent="    "), flush=True)
            case EventKind.AUDIT_INPUT:
                self._section_break(f"sent to {event.who}, verbatim")
                print(wrap(event.text), flush=True)
            case EventKind.CALL:
                self._section_break(self._worker(event))
                print(wrap(clip(event.text, _ARG_LIMIT), subsequent="    "), flush=True)
            case EventKind.RESULT:
                self._section_break(self._worker(event))
                label = f"{event.who}: " if event.who else ""
                mark = "!" if self.is_error(event.text) else "←"
                summary = clip(f"{mark} {label}{self.digest(event.text)}", _ARG_LIMIT)
                print(wrap(summary, subsequent="    "), flush=True)

    def _worker(self, event: Event) -> str:
        """Who is doing this work.

        `event.stream` resolves to the subagent's own name once it has made a
        model call, and is a short stream id until then. Either way it separates
        concurrent investigators, which one shared heading cannot.
        """
        if event.root:
            return self.orchestrator
        return event.stream or "delegated"

    def _section_break(self, label: str) -> None:
        """A dim label, once, when the speaker changes."""
        if label == self._section:
            return
        text = f"{_LABEL}{label}{_RESET}" if self.colour else label
        print(f"\n{text}", flush=True)
        self._section = label
