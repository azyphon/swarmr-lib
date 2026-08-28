"""Keeping the first round of delegation free of the orchestrator's framing.

A subagent's system prompt already carries its domain, method, tools and output
contract. The only run-specific input it receives is the `task` call's
description, so that description should carry the symptom and nothing else.

Left to the model, it does not. Observed in real runs, the orchestrator restated
each specialist's own checklist back to it, and worse, pre-framed the problem per
domain: telling the network specialist that traffic fails *because pods will not
start*, and telling the platform specialist to consider *the heterogeneous
amd64/arm64 cluster*. Both hand over a conclusion the specialist is supposed to
reach independently, and the second names the exact hypothesis under test.

Prompt instructions did not hold — a model asked to be brief still wants to be
helpful. So this is enforced by the harness instead: on the FIRST dispatch to
each subagent, the description is replaced with the caller's own request. Later
dispatches pass through untouched, because by then the orchestrator genuinely
knows something and a targeted follow-up is the point of a second round.

The adjudicator is exempt: its payload is a finished hypothesis, which is
exactly what it must receive.

This is not a workaround for a careless model. The harness's own task-tool
description says "Put full detail in the prompt and state exactly what it should
return", so verbose briefings are the documented behaviour; a prompt rule asking
for one sentence is arguing with the tool schema. Rewriting the argument is the
pattern deepagents itself uses for this class of problem — see
NemotronToolCallShim, which repairs tool arguments the same way.

This module is the rule alone. The middleware that applies it lives in
`core.middleware`, so the rule can be read, tested and reused — the event reader
displays what a subagent will actually receive — without importing the agent
framework.
"""

from __future__ import annotations

__all__ = ["effective_briefing"]


def effective_briefing(
    request: str,
    who: str,
    exempt: tuple[str, ...],
    already_briefed: set[str],
) -> str | None:
    """The briefing a subagent will actually receive, or None to pass through.

    Shared by the middleware that rewrites the payload and by the reader that
    displays it. A tool call is displayed the moment the model emits it, before
    any middleware runs, so without a shared rule the terminal shows text the
    subagent never saw.
    """
    if not who or who in exempt or who in already_briefed or not request:
        return None
    return request
