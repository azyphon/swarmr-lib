"""Stream-tag attribution: per run, or two runs corrupt each other.

The map used to be module state cleared at the start of every run, so a second
investigation started over MCP wiped the first one's names mid-flight and then
wrote into the same namespace. Both regressions are pinned here: instances are
independent, and every segment of a namespace is registered, because the stream
reports only the outer one and registering just the last never matched.
"""

from __future__ import annotations

import pytest

from swarmr.core.attribution import Attribution, current_namespace, tag_of

# A tool's checkpoint namespace: the task node, then the subagent's own graph.
NAMESPACE = "tools:aaaa1111|tools:bbbb2222"


@pytest.mark.parametrize(
    ("namespace", "expected"),
    [
        ("tools:aaaa1111", "aaaa"),
        ("tools:aaaa1111|tools:bbbb2222", "bbbb"),
        ("bare", "bare"),
        ("tools:ab", "ab"),
        ("", ""),
    ],
    ids=["one-segment", "last-segment-wins", "no-prefix", "shorter-than-four", "empty"],
)
def test_tag_of_takes_four_characters_of_the_last_colon_segment(
    namespace: str, expected: str
) -> None:
    assert tag_of(namespace) == expected


def test_note_registers_every_segment_of_the_namespace() -> None:
    """`stream_mode="updates"` reports only the outer segment, so registering
    just the inner one silently never matched and every line showed a raw tag."""
    attribution = Attribution()
    attribution.note("network", namespace=NAMESPACE)
    assert attribution.resolve("aaaa") == "network"
    assert attribution.resolve("bbbb") == "network"


def test_the_first_name_noted_for_a_tag_wins() -> None:
    """A tag belongs to one subagent for the life of the run; a later writer
    reassigning it would relabel that subagent's earlier trail lines."""
    attribution = Attribution()
    attribution.note("network", namespace="tools:aaaa1111")
    attribution.note("storage", namespace="tools:aaaa1111")
    assert attribution.resolve("aaaa") == "network"


def test_an_unknown_tag_resolves_to_nothing() -> None:
    assert Attribution().resolve("aaaa") is None


def test_the_root_agent_has_no_namespace_and_is_labelled_root() -> None:
    assert Attribution().label(()) == "root"


def test_label_shows_the_raw_tag_until_the_subagent_has_been_named() -> None:
    """The name arrives with that subagent's first model call, so early lines
    carry the tag. Honest: guessing from dispatch order breaks under concurrency."""
    attribution = Attribution()
    assert attribution.label(("tools:bbbb2222",)) == "bbbb"
    attribution.note("network", namespace=NAMESPACE)
    assert attribution.label(("tools:bbbb2222",)) == "network"


def test_label_reads_the_innermost_namespace_segment() -> None:
    attribution = Attribution()
    attribution.note("network", namespace="tools:aaaa1111")
    assert attribution.label(("tools:xxxx", "tools:aaaa1111")) == "network"


def test_two_attributions_share_no_state() -> None:
    """The regression: one run's names must not be visible to, or erasable by,
    another run started while the first is still going."""
    first, second = Attribution(), Attribution()
    first.note("network", namespace=NAMESPACE)
    second.note("storage", namespace=NAMESPACE)
    assert first.resolve("bbbb") == "network"
    assert second.resolve("bbbb") == "storage"


def test_noting_outside_a_running_graph_is_a_no_op() -> None:
    """Best-effort by design: with no namespace to bind, the trail is merely
    less readable, and a changed LangGraph API must not break a run."""
    attribution = Attribution()
    attribution.note("network")
    assert current_namespace() == ""
    assert attribution.label(("tools:bbbb2222",)) == "bbbb"
