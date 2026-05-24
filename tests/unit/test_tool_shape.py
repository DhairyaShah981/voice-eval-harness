"""ToolShapeAssertion — runtime tool-args contract validation."""

from __future__ import annotations

from voice_eval_harness.assertions.base import build_assertion
from voice_eval_harness.core.models import AssertionSpec, CallSummary


def _summary(invocations: list[dict]) -> CallSummary:
    return CallSummary(tool_invocations=invocations)


def test_tool_not_called_fails() -> None:
    spec = AssertionSpec(kind="tool_shape", tool_name="get_slots", require={})
    res = build_assertion(spec).evaluate([], _summary([]))
    assert not res.passed
    assert "never called" in res.detail


def test_required_field_missing() -> None:
    spec = AssertionSpec(kind="tool_shape", tool_name="get_slots",
                         require={"day_of_week": {"type": "string"}})
    res = build_assertion(spec).evaluate([], _summary([
        {"name": "get_slots", "args": {}},
    ]))
    assert not res.passed
    assert "day_of_week" in res.detail


def test_type_mismatch() -> None:
    spec = AssertionSpec(kind="tool_shape", tool_name="book",
                         require={"count": {"type": "integer"}})
    res = build_assertion(spec).evaluate([], _summary([
        {"name": "book", "args": {"count": "two"}},
    ]))
    assert not res.passed
    assert "integer" in res.detail


def test_enum_in_set() -> None:
    spec = AssertionSpec(
        kind="tool_shape", tool_name="book",
        require={"day": {"type": "string",
                         "in": ["monday", "tuesday", "wednesday"]}},
    )
    bad = build_assertion(spec).evaluate([], _summary([
        {"name": "book", "args": {"day": "funday"}},
    ]))
    good = build_assertion(spec).evaluate([], _summary([
        {"name": "book", "args": {"day": "tuesday"}},
    ]))
    assert not bad.passed
    assert "funday" in bad.detail
    assert good.passed


def test_min_max() -> None:
    spec = AssertionSpec(
        kind="tool_shape", tool_name="lookup",
        require={"window": {"type": "integer", "min": 1, "max": 30}},
    )
    too_big = build_assertion(spec).evaluate([], _summary([
        {"name": "lookup", "args": {"window": 99}},
    ]))
    just_right = build_assertion(spec).evaluate([], _summary([
        {"name": "lookup", "args": {"window": 7}},
    ]))
    assert not too_big.passed
    assert just_right.passed


def test_allow_extra_false_catches_typos() -> None:
    spec = AssertionSpec(
        kind="tool_shape", tool_name="lookup",
        require={"window": {"type": "integer"}},
        allow_extra=False,
    )
    res = build_assertion(spec).evaluate([], _summary([
        {"name": "lookup", "args": {"window": 7, "windwo": "typo"}},
    ]))
    assert not res.passed
    assert "windwo" in res.detail
