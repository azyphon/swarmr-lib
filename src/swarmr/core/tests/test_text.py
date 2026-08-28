"""Shared text helpers.

`content_text` existed in two modules before this, which is why a provider
answer arriving as content blocks was dropped in one place and handled in the
other. One definition, tested once.
"""

from __future__ import annotations

from swarmr.core.text import clip, content_text, flatten, wrap


class TestContentText:
    def test_plain_string(self) -> None:
        assert content_text("  hello  ") == "hello"

    def test_content_blocks_are_flattened(self) -> None:
        """The shape that silently dropped a finished report."""
        blocks = [
            {"type": "text", "text": "first"},
            {"type": "thinking", "thinking": "ignored"},
            {"type": "text", "text": "second"},
        ]
        assert content_text(blocks) == "first\nsecond"

    def test_unknown_shapes_yield_nothing(self) -> None:
        assert content_text(None) == ""
        assert content_text(42) == ""
        assert content_text([{"type": "image"}]) == ""


class TestClip:
    def test_short_text_is_untouched(self) -> None:
        assert clip("short", 20) == "short"

    def test_clipping_breaks_at_a_word_boundary(self) -> None:
        """A half word ending in an ellipsis is harder to read than a short one."""
        clipped = clip("the quick brown fox jumps over", 18)
        assert clipped.endswith("…")
        assert "brow…" not in clipped

    def test_whitespace_is_collapsed(self) -> None:
        assert clip("a\n  b\tc", 40) == "a b c"


class TestWrap:
    def test_long_lines_wrap_with_indent(self) -> None:
        text = " ".join(["word"] * 60)
        wrapped = wrap(text, indent="  ")
        assert all(line.startswith("  ") for line in wrapped.splitlines() if line)
        assert len(wrapped.splitlines()) > 1

    def test_paragraph_breaks_survive(self) -> None:
        """A report's structure is part of its readability."""
        wrapped = wrap("first\n\nsecond")
        assert "" in wrapped.splitlines()

    def test_nothing_is_truncated(self) -> None:
        text = " ".join(f"w{i}" for i in range(80))
        wrapped = wrap(text)
        assert "…" not in wrapped
        for word in text.split():
            assert word in wrapped


def test_flatten_keeps_every_word() -> None:
    assert flatten("  a\n\nb   c ") == "a b c"
