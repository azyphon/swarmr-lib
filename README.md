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

## Install

Distributed from git, not an index. To run it:

```bash
uv tool install git+https://github.com/azyphon/swarmr-lib \
  --with git+https://github.com/azyphon/swarmr-k8s-incident \
  --with-executables-from swarmr-k8s-incident
```

`--with` puts the team in the same environment, which is what discovery
requires. `--with-executables-from` is separate and easy to miss: without it
only core's `teams` and `teams-mcp` reach your PATH, and a team's own commands
stay inside the tool environment. Omit it if the team ships none. A plain venv
works too:

```bash
python3 -m venv .venv
.venv/bin/pip install git+https://github.com/azyphon/swarmr-lib
.venv/bin/pip install git+https://github.com/azyphon/swarmr-k8s-incident
```

**Same environment** is the only rule. Core discovers teams through the
metadata of installed distributions, not through paths, so where the repos sit
on disk is irrelevant and two virtualenvs are two disconnected worlds.

**Core first.** A team declares `swarmr>=1.0,<2`, and pip resolves that against
an index it will not find core on. Installing core from git first satisfies the
requirement; pip then leaves the installed copy alone. The dependency stays a
version rather than a git URL so that moving to an index later changes nothing
in the team.

Then a model key, in the directory you run from:

```bash
printf 'KIMI_API_KEY=sk-…\nKIMI_MODEL=kimi-for-coding\n' > .env && chmod 600 .env
```

Loading walks up from the current directory, then falls back to `~/.env`;
`KIMI_ENV_FILE` overrides both.

## CLI

```bash
teams --list
teams --target <team>      # profile the target, then exit
teams <team> "the symptom, as prose"
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
      "command": "teams-mcp",
      "cwd": "/abs/path/to/your/working/dir",
      "timeout": 0
    }
  }
}
```

`cwd` is where the server looks for `.env` and any team credentials, so point
it at the directory you would otherwise `cd` into. If `teams-mcp` is not on the
PATH your MCP client sees, give the absolute path to it instead.

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
dependencies = ["swarmr>=1.0,<2", "whatever-sdk>=1"]

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
`swarmr.teams` entry-point group name. Pin `swarmr>=1.0,<2`.

`core.testing` ships `EXAMPLE_TEAM`, `TeamFactory`, `JobFactory` and `GraphStub`
so a team in another distribution tests against the same stand-ins core does.

## Development

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest && ruff check . && pyright
```

Activate the venv rather than calling `.venv/bin/…` directly: pyright resolves
the interpreter from PATH, so unactivated it type-checks against a Python that
has none of the dependencies and reports every import as unresolved. Without
activating, pass `--pythonpath .venv/bin/python`.

The suite passes with **no team installed**, which is the proof that core stands
alone. Discovery is exercised against an injected entry point pointing at
`core.testing:EXAMPLE_TEAM` — the same path a third-party distribution takes.
The complementary half, that a real installed team stays unimported until run,
is asserted in each team's own suite, where a team to not-import exists.

**Tests live beside the code they test.** `core/tests` may not import from any
team; `core/tests/test_render.py` renders an invented foreman-and-welder team to
prove exactly that. The wheel excludes every `tests/` directory;
`core/testing.py` is shipped deliberately.
