"""Token accounting: whose context went where, joined from two provider fields.

The numbers are reported to users and used to decide which specialist is
expensive, so misattribution is worse than no number at all. The interleaving
case is the one that matters: subagents run concurrently, so the owner of a
model call is fixed at its start and looked up by run id at its end.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from swarmr.core.usage import UsageTracker, langsmith_enabled


@pytest.fixture(autouse=True)
def no_tracing(monkeypatch: pytest.MonkeyPatch) -> None:
    """LangSmith is environment-driven, so a snapshot must not read the dev's env."""
    for key in (
        "LANGSMITH_TRACING",
        "LANGCHAIN_TRACING_V2",
        "LANGSMITH_API_KEY",
        "LANGCHAIN_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)


def metadata(
    input_tokens: int, output_tokens: int, reasoning: int = 0, cached: int = 0
) -> dict[str, Any]:
    """`usage_metadata` in the shape a provider attaches it to the reply message."""
    payload: dict[str, Any] = {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
    }
    if reasoning:
        payload["output_token_details"] = {"reasoning": reasoning}
    if cached:
        payload["input_token_details"] = {"cache_read": cached}
    return payload


def response(usage: dict[str, Any] | None = None, **llm_output: Any) -> LLMResult:
    message = AIMessage(content="ok", usage_metadata=usage)  # type: ignore[arg-type]
    return LLMResult(
        generations=[[ChatGeneration(message=message)]],
        llm_output=llm_output or None,
    )


def record(tracker: UsageTracker, result: LLMResult, owner: str | None = None) -> None:
    """One complete model call through the callback surface the graph uses."""
    run_id = uuid4()
    tracker.on_chat_model_start(
        {},
        [[]],
        run_id=run_id,
        metadata={"lc_agent_name": owner} if owner else None,
    )
    tracker.on_llm_end(result, run_id=run_id)


def test_a_tagged_call_is_attributed_to_the_subagent_that_made_it() -> None:
    tracker = UsageTracker(root_label="commander")
    record(tracker, response(metadata(10, 4)), owner="network")
    assert tracker.snapshot()["per_agent"]["network"]["total"] == 14


def test_an_untagged_call_belongs_to_the_root_agent_the_team_named() -> None:
    """lc_agent_name is absent exactly for the root agent, so this is not a
    catch-all: `core` must use the team's own word for that role."""
    tracker = UsageTracker(root_label="commander")
    record(tracker, response(metadata(10, 4)))
    assert list(tracker.snapshot()["per_agent"]) == ["commander"]


def test_counts_accumulate_across_calls_by_the_same_agent() -> None:
    tracker = UsageTracker()
    record(tracker, response(metadata(10, 4)), owner="network")
    record(tracker, response(metadata(5, 1)), owner="network")
    row = tracker.snapshot()["per_agent"]["network"]
    assert (row["calls"], row["input"], row["output"], row["total"]) == (2, 15, 5, 20)


def test_ownership_survives_two_calls_finishing_out_of_order() -> None:
    """Subagents run concurrently, so calls interleave. Attribution is keyed on
    the run id, not on whichever call started last."""
    tracker = UsageTracker()
    first, second = uuid4(), uuid4()
    tracker.on_chat_model_start({}, [[]], run_id=first, metadata={"lc_agent_name": "a"})
    tracker.on_chat_model_start({}, [[]], run_id=second, metadata={"lc_agent_name": "b"})
    tracker.on_llm_end(response(metadata(7, 0)), run_id=second)
    tracker.on_llm_end(response(metadata(3, 0)), run_id=first)
    rows = tracker.snapshot()["per_agent"]
    assert (rows["a"]["input"], rows["b"]["input"]) == (3, 7)


def test_totals_sum_every_agent() -> None:
    tracker = UsageTracker()
    record(tracker, response(metadata(10, 4, reasoning=2, cached=6)), owner="network")
    record(tracker, response(metadata(1, 1)), owner="critic")
    totals = tracker.totals()
    assert totals.calls == 2
    assert totals.total_tokens == 16
    assert (totals.reasoning_tokens, totals.cached_tokens) == (2, 6)


def test_snapshot_orders_agents_by_total_tokens_descending() -> None:
    """The listing is a ranking: the point is seeing where context went first."""
    tracker = UsageTracker()
    record(tracker, response(metadata(10, 0)), owner="small")
    record(tracker, response(metadata(9_000, 100)), owner="large")
    record(tracker, response(metadata(500, 0)), owner="medium")
    assert list(tracker.snapshot()["per_agent"]) == ["large", "medium", "small"]


def test_snapshot_reports_the_number_of_model_calls_behind_the_totals() -> None:
    tracker = UsageTracker()
    record(tracker, response(metadata(10, 4)), owner="network")
    record(tracker, response(metadata(10, 4)), owner="critic")
    snap = tracker.snapshot()
    assert (snap["model_calls"], snap["total_tokens"]) == (2, 28)


def test_reasoning_and_cache_read_details_land_in_their_own_fields() -> None:
    """Reasoning is already inside output tokens; cached input is billed apart.
    Folding either into the wrong field misstates the cost."""
    tracker = UsageTracker()
    record(tracker, response(metadata(100, 40, reasoning=30, cached=64)), owner="critic")
    row = tracker.snapshot()["per_agent"]["critic"]
    assert (row["input"], row["output"]) == (100, 40)
    assert (row["reasoning"], row["cached"]) == (30, 64)


def test_message_usage_metadata_wins_over_the_providers_llm_output() -> None:
    """A provider that reports both must not be counted twice or from the
    looser field: the message is the authoritative one."""
    tracker = UsageTracker()
    result = response(
        metadata(10, 4),
        token_usage={"prompt_tokens": 9_999, "completion_tokens": 9_999},
    )
    record(tracker, result, owner="network")
    assert tracker.snapshot()["per_agent"]["network"]["total"] == 14


@pytest.mark.parametrize(
    "llm_output",
    [
        {"token_usage": {"prompt_tokens": 12, "completion_tokens": 3}},
        {"usage_metadata": {"input_tokens": 12, "output_tokens": 3}},
    ],
    ids=["openai-aliases", "canonical-names"],
)
def test_usage_falls_back_to_llm_output_when_the_message_carries_none(
    llm_output: dict[str, Any],
) -> None:
    """OpenAI-compatible providers report prompt/completion instead, and a run
    against one of those must not read as zero tokens."""
    tracker = UsageTracker()
    record(tracker, response(None, **llm_output), owner="network")
    row = tracker.snapshot()["per_agent"]["network"]
    assert (row["input"], row["output"]) == (12, 3)


def test_a_response_reporting_nothing_is_still_counted_as_a_call() -> None:
    """Otherwise a provider that omits usage looks like an agent that never ran."""
    tracker = UsageTracker()
    record(tracker, response(None), owner="network")
    row = tracker.snapshot()["per_agent"]["network"]
    assert (row["calls"], row["total"]) == (1, 0)


@pytest.mark.parametrize(
    ("flag", "key", "expected"),
    [
        ("true", "LANGSMITH_API_KEY", True),
        ("1", "LANGSMITH_API_KEY", True),
        ("yes", "LANGCHAIN_API_KEY", True),
        ("false", "LANGSMITH_API_KEY", False),
        ("true", None, False),
        ("", "LANGSMITH_API_KEY", False),
    ],
)
def test_langsmith_is_enabled_only_with_both_a_flag_and_a_key(
    monkeypatch: pytest.MonkeyPatch, flag: str, key: str | None, expected: bool
) -> None:
    """Claiming "traces are in your project" without a key sends a user looking
    for output that was never uploaded."""
    monkeypatch.setenv("LANGSMITH_TRACING", flag)
    if key:
        monkeypatch.setenv(key, "sk-test")
    assert langsmith_enabled() is expected
