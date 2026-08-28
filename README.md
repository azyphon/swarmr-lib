# swarmr

Teams of [Deep Agents](https://github.com/langchain-ai/deepagents) domain
specialists, exposed two ways: a streaming terminal CLI and an MCP server.

This is the core distribution. It ships **no team**. Teams live in their own
repositories, depend on this one, and are found through installed metadata.

## How it fits together

**Dependencies flow one way: teams → core.** Teams never import each other, and
`core` knows nothing about any domain — no role names, no payload shapes, not
even what a failed tool result looks like. Nothing here names a team;
`pip install` and `pip uninstall` are the whole lifecycle.

**Nothing loads until it is used.** Discovery reads installed metadata and
imports nothing. A team's heavyweight fields are declared with `Lazy` and
resolved on first call, so listing teams — which the MCP server does on every
start, to read each team's `name`, `summary` and `description` — never loads an
agent stack.

**A team supplies its own vocabulary** (`orchestrator`, `audit_agents`,
`digest`, `is_error`, `report_tool`, `default_request`, `recursion_limit`), so
`core` renders and records without assuming any role, payload or limit exists.

## Setup

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
printf 'KIMI_API_KEY=sk-…\nKIMI_MODEL=kimi-for-coding\n' > .env && chmod 600 .env
```

Then install whichever teams you want, into the same environment:

```bash
.venv/bin/pip install git+https://github.com/azyphon/swarmr-k8s-incident
```

**Same environment** is the only rule. Core discovers teams through the
metadata of installed distributions, not through paths, so where the repos sit
on disk is irrelevant and two virtualenvs are two disconnected worlds.

**Core first.** A team declares `swarmr>=0.1,<0.2`, which pip resolves against
an index. Until this package is published to one, installing a team into an
empty environment fails with `No matching distribution found for swarmr`;
installing core from git first satisfies the requirement.

## CLI

```bash
.venv/bin/teams --list
.venv/bin/teams --target <team>      # profile the target, then exit
.venv/bin/teams <team> "the symptom, as prose"
```

Output shows delegation live: the plan, parallel dispatches, each tool call with
a digest of its result, every subagent's verdict attributed by name, per-agent
token counts.

## MCP

```json
{
  "mcpServers": {
    "swarmr": {
      "type": "stdio",
      "command": "/abs/path/.venv/bin/python",
      "args": ["-m", "swarmr.server"],
      "cwd": "/abs/path",
      "timeout": 0
    }
  }
}
```

Tools: `start_<team>` for every installed team, plus `check_task` and
`list_tasks`. Runs take minutes and MCP is request/response, so `start_*`
returns a job id immediately and `check_task` long-polls — it returns the moment
a specialist is dispatched or reports, with only the trail steps you have not
seen. One named tool per team, not a generic `run(team, task)`, because the
calling model routes on tool descriptions.

Install a team, restart the server, and its tool appears. No configuration
changes.

## Adding a team

Create a distribution that declares a `Team`, and advertise it:

```toml
[project]
dependencies = ["swarmr>=0.1,<0.2", "whatever-sdk>=1"]

[project.entry-points."swarmr.teams"]
my_team = "my_package:TEAM"
```

```python
from swarmr.core.team import Lazy, Member, Team

TEAM = Team(
    name="my_team",
    summary="One sentence, shown in tool listings.",
    description="What the calling model routes on: symptoms, not subject area.",
    build=Lazy("my_package.agent:build"),  # imported on first run
    profile=Lazy("my_package.agent:profile"),  # optional, no model needed
    members=(Member("lead", "what it investigates"),),
)
```

That is the whole coupling. The CLI and the MCP server iterate discovery, so the
team gets a `start_my_team` tool and a CLI command with no further edits, and
`pip uninstall` unregisters it. The only rule is that anything importing an
agent framework, model SDK or domain client goes behind `Lazy`.

### The ABI

Everything a team may depend on, and the surface a minor release may move:
`Team`, `RunContext`, `TeamBuild`, `Member`, `Lazy`, `TeamError`, `Attribution`,
the middleware in `core.middleware`, the stubs in `core.testing`, and the
`swarmr.teams` entry-point group name. Pin `swarmr>=0.1,<0.2`.

`core.testing` ships `EXAMPLE_TEAM`, `TeamFactory`, `JobFactory` and `GraphStub`
so a team in another distribution tests against the same stand-ins core does.

## Tests

```bash
.venv/bin/python -m pytest
.venv/bin/ruff check . && .venv/bin/pyright
```

The suite passes with **no team installed**, which is the proof that core stands
alone. Discovery is exercised against an injected entry point pointing at
`core.testing:EXAMPLE_TEAM` — the same path a third-party distribution takes.
The complementary half, that a real installed team stays unimported until run,
is asserted in each team's own suite, where a team to not-import exists.

**Tests live beside the code they test.** `core/tests` may not import from any
team; `core/tests/test_render.py` renders an invented foreman-and-welder team to
prove exactly that. The wheel excludes every `tests/` directory;
`core/testing.py` is shipped deliberately.
