"""``assert_tool_shape`` — runtime tool-args contract validator.

The structural linter catches schema bugs in agent JSON at build-time
(RTL-010 / RTL-011 — empty `required`, missing property descriptions).
This assertion catches the runtime equivalent: when the agent actually
calls a tool, does the payload conform to the declared schema?

Examples:

    asserts:
      - assert_tool_shape:
          tool_name: get_available_slots
          require:
            day_of_week: { type: string, in: [monday, tuesday, ..., sunday] }
            window_days: { type: integer, min: 1, max: 30 }
          allow_extra: false   # default: true

"""

from __future__ import annotations

from typing import Any

from voice_eval_harness.assertions.base import Assertion
from voice_eval_harness.core.models import (
    AssertionResult,
    CallSummary,
    TranscriptEvent,
)


def _check_value(field: str, value: Any, rule: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    expected_type = rule.get("type")
    type_map = {
        "string": str, "integer": int, "number": (int, float),
        "boolean": bool, "array": list, "object": dict,
    }
    if expected_type and expected_type in type_map:
        py_type = type_map[expected_type]
        if not isinstance(value, py_type):
            errors.append(
                f"{field}: expected type {expected_type}, "
                f"got {type(value).__name__} ({value!r})"
            )
            return errors  # don't chain further checks on a type mismatch
    if "in" in rule and value not in rule["in"]:
        errors.append(f"{field}: value {value!r} not in allowed set {rule['in']}")
    if "min" in rule and isinstance(value, (int, float)) and value < rule["min"]:
        errors.append(f"{field}: {value} < min {rule['min']}")
    if "max" in rule and isinstance(value, (int, float)) and value > rule["max"]:
        errors.append(f"{field}: {value} > max {rule['max']}")
    if "regex" in rule:
        import re
        if not isinstance(value, str) or not re.search(rule["regex"], value):
            errors.append(f"{field}: {value!r} does not match /{rule['regex']}/")
    return errors


class ToolShapeAssertion(Assertion):
    kind = "tool_shape"

    def evaluate(
        self, transcript: list[TranscriptEvent], summary: CallSummary,
    ) -> AssertionResult:
        tool_name = self.params.get("tool_name")
        require: dict[str, Any] = self.params.get("require") or {}
        allow_extra = bool(self.params.get("allow_extra", True))
        if not tool_name:
            return AssertionResult(
                kind=self.kind, passed=False,
                detail="assert_tool_shape: missing 'tool_name'",
            )
        invocations = [
            t for t in summary.tool_invocations
            if t.get("name") == tool_name
        ]
        if not invocations:
            return AssertionResult(
                kind=self.kind, passed=False,
                detail=f"tool {tool_name!r} was never called",
            )
        errors: list[str] = []
        for idx, inv in enumerate(invocations):
            args: dict[str, Any] = inv.get("args") or {}
            for field, rule in require.items():
                if field not in args:
                    errors.append(f"call[{idx}].{field}: required field missing")
                    continue
                errors.extend(_check_value(f"call[{idx}].{field}", args[field], rule))
            if not allow_extra:
                extras = set(args) - set(require)
                if extras:
                    errors.append(
                        f"call[{idx}]: unexpected extra args {sorted(extras)}"
                    )
        ok = not errors
        return AssertionResult(
            kind=self.kind, passed=ok,
            detail="" if ok else "; ".join(errors[:5]),
        )


_BUILTIN_TOOL_SHAPE = ToolShapeAssertion


def register(builtin_dict: dict[str, type[Assertion]]) -> None:
    """Called from assertions.base.BUILTIN_ASSERTIONS construction."""
    builtin_dict[_BUILTIN_TOOL_SHAPE.kind] = _BUILTIN_TOOL_SHAPE
