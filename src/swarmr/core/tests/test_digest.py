"""The shape-only fallback digest.

It is the summary a team gets for free, so it must never claim to understand a
payload: shape, count, keys, line count. Anything more is the team's job.
"""

from __future__ import annotations

import json

import pytest

from swarmr.core.digest import generic_digest


def test_json_object_reports_shape_only() -> None:
    payload = json.dumps({"seam": 4, "gap_mm": 2.5, "pass": False})
    assert generic_digest(payload) == "3 fields [seam, gap_mm, pass]"


def test_json_array_reports_its_length() -> None:
    assert generic_digest("[1, 2, 3]") == "3 items"


def test_truncated_json_is_reported_as_such() -> None:
    assert "truncated json" in generic_digest('{"kind": "Pod", "items": [{"na')


def test_text_reports_line_count() -> None:
    assert generic_digest("a\nb\nc").startswith("3 lines")


@pytest.mark.parametrize("payload", ["", "   "])
def test_empty_payloads_read_as_empty(payload: str) -> None:
    assert generic_digest(payload) == "empty"


def test_no_domain_vocabulary_is_recognised() -> None:
    """One team's "tool error" prefix used to be special-cased here."""
    assert generic_digest("tool error: unknown kind 'x'").startswith("1 lines")
