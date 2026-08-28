"""The Deep Agents harness vocabulary `core` reads off the stream.

These names belong to deepagents, not to us and not to any domain: the built-in
delegation tool, the key naming the subagent inside its arguments, and the
planning tool. They were spelled out twice — once as constants in `briefing`,
once as bare literals in `events` — which is two owners for one upstream
contract. One definition, so an upstream rename is a single edit.
"""

from __future__ import annotations

__all__ = ["DESCRIPTION_KEY", "PLAN_TOOL", "PROMPT_KEY", "SUBAGENT_KEY", "TASK_TOOL"]

TASK_TOOL = "task"
PLAN_TOOL = "write_todos"
SUBAGENT_KEY = "subagent_type"
DESCRIPTION_KEY = "description"
PROMPT_KEY = "prompt"
