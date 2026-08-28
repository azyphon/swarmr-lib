"""Formatting a job for a calling agent to read.

MCP clients render a tool result as text and collapse long structured payloads,
so a JSON object with a dozen keys shows its first few fields and hides the rest
behind an expand shortcut. The delegation trail is the whole point of a poll, so
it is emitted as plain text with the trail near the top rather than as JSON.

Everything here formats an already-captured snapshot dict. It never touches a
live `Job`: the worker thread mutates the trail, counters and verdict map while
a poll is being served, so reading those containers directly can iterate a
mutating dict or mix fields from two different instants.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "format_roster",
    "format_snapshot",
    "format_snapshot_line",
    "format_usage",
]


def format_usage(usage: dict[str, Any]) -> str:
    """Per-agent token counts, biggest consumer first.

    Reported per agent rather than as one total because that is the number that
    tells you where context is going: one subagent re-reading large objects can
    cost more than the rest of the team combined.

    The ranking is applied here rather than trusted from the caller. The heading
    is a promise to the reader, and a producer that hands over an unsorted
    mapping would quietly break it.
    """
    rows = usage.get("per_agent") or {}
    if not rows:
        return ""
    width = max(len(name) for name in rows)
    lines = ["", "TOKENS  (input / output, reasoning included in output)"]
    ranked = sorted(rows.items(), key=lambda kv: -int(kv[1].get("total") or 0))
    for name, u in ranked:
        line = (
            f"  {name:<{width}}  {u['total']:>7,} total"
            f"  = {u['input']:>7,} in + {u['output']:>6,} out"
            f"  over {u['calls']:>2} calls"
        )
        if u.get("reasoning"):
            line += f"  ({u['reasoning']:,} reasoning)"
        if u.get("cached"):
            line += f"  ({u['cached']:,} cached)"
        lines.append(line)
    lines.append(
        f"  {'TOTAL':<{width}}  {usage.get('total_tokens', 0):>7,} total"
        f"  over {usage.get('model_calls', 0)} model calls"
    )
    if usage.get("langsmith"):
        lines.append("  LangSmith tracing is on; full traces are in your project.")
    return "\n".join(lines)


def format_roster(team_name: str, roster: str) -> str:
    """The line-up, so a caller can see who is on the case before work starts."""
    if not roster:
        return ""
    return f"\n{team_name} roster:\n{roster}"


def format_snapshot(snap: dict[str, Any], running_footer: str = "") -> str:
    """Human-readable snapshot: header, delegation trail, verdicts, report.

    Args:
        snap: A captured snapshot dict, never a live `Job`.
        running_footer: What to tell the caller while the run is still going —
            how to poll again, in whatever vocabulary the calling surface has.
            Supplied by that surface: naming a tool here would put the MCP
            server's API inside the domain-free layer, and a renamed tool would
            leave `core` printing instructions that no longer exist.
    """
    if error := snap.get("lookup_error"):
        return str(error)

    lines = [_header(snap)]

    if trail := snap.get("trail"):
        total = snap.get("trail_total")
        header = (
            "NEW ACTIVITY since your last poll"
            if snap.get("trail_is_delta")
            else "DELEGATION"
        )
        if total:
            header += f"  ({len(trail)} of {total} steps)"
        lines += ["", header, *_grouped(trail)]
    elif snap.get("trail_is_delta"):
        lines += ["", "NEW ACTIVITY since your last poll: none yet."]

    if verdicts := snap.get("verdicts"):
        lines += ["", "VERDICTS"]
        lines += [f"  {who:<10} {headline}" for who, headline in verdicts.items()]

    if calls := snap.get("tool_calls"):
        counts = ", ".join(f"{name} x{count}" for name, count in calls.items())
        lines += ["", f"TOOL CALLS  {counts}"]

    if usage := snap.get("usage"):
        lines.append(format_usage(usage))

    state = snap.get("state")
    if state == "done":
        # Emitted even when empty: a finished run that produced no text used to
        # fall through to the "still running, poll again" footer, so a
        # well-behaved client polled a settled job forever.
        lines += ["", "REPORT", str(snap.get("report") or "(no report text)")]
    elif state == "failed":
        lines += ["", f"ERROR  {snap.get('error')}"]
    elif running_footer:
        lines += ["", running_footer]
    return "\n".join(lines)


def _grouped(trail: Any) -> list[str]:
    """Group consecutive steps under the agent that took them.

    The same layout the terminal uses: a heading when the actor changes, rather
    than an inline tag repeated on every line.
    """
    lines: list[str] = []
    current: str | None = None
    for entry in trail:
        if isinstance(entry, (list, tuple)) and len(entry) >= 2:
            author, text = str(entry[0]), str(entry[1])
        else:
            author, text = "", str(entry)
        if author and author != current:
            lines.append(author)
            current = author
        lines.append(f"  {text}")
    return lines


def _header(snap: dict[str, Any]) -> str:
    parts = [
        f"{snap.get('team')} job {snap.get('job')}",
        str(snap.get("state")),
        f"{snap.get('elapsed_seconds')}s",
        f"milestone={snap.get('milestone', 0)}",
    ]
    if waiting := snap.get("waiting_on"):
        parts.append(f"waiting on: {', '.join(waiting)}")
    header = " · ".join(parts)
    target = snap.get("target")
    return f"{header}\n{target}" if target else header


def format_snapshot_line(snap: dict[str, Any]) -> str:
    """One line per job, for listings."""
    return (
        f"{snap.get('job')}  {snap.get('team')!s:<14} "
        f"{snap.get('state')!s:<8} {snap.get('elapsed_seconds'):>6}s  "
        f"{str(snap.get('request', ''))[:60]}"
    )
