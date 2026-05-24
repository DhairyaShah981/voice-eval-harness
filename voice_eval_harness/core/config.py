"""YAML loader for voxeval.yaml.

Responsibilities:
  - Expand ``${VAR}`` references against ``os.environ`` (and an optional
    ``.env`` file in the project root).
  - Normalize the friendly assert shorthand (``assert_contains: [...]``,
    bare ``"assert_no_crash"``, etc.) into uniform ``AssertionSpec`` dicts.
  - Hand the normalized dict to Pydantic for full validation.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml

from voice_eval_harness.core.models import EvalSuite

_ENV_REF = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)\}")

_ASSERT_PREFIX = "assert_"


def _expand_env(value: Any, env: dict[str, str]) -> Any:
    if isinstance(value, str):
        def repl(m: re.Match[str]) -> str:
            return env.get(m.group(1), "")
        return _ENV_REF.sub(repl, value)
    if isinstance(value, list):
        return [_expand_env(v, env) for v in value]
    if isinstance(value, dict):
        return {k: _expand_env(v, env) for k, v in value.items()}
    return value


def _load_dotenv(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def _normalize_assert_entry(entry: Any) -> dict[str, Any]:
    """Turn one assert spec from YAML into ``{"kind": str, ...}``.

    Accepted shapes:
      "assert_no_crash"                     → {"kind": "no_crash"}
      {"assert_contains": ["x", "y"]}       → {"kind": "contains", "values": ["x", "y"]}
      {"assert_contains": "foo"}            → {"kind": "contains", "values": ["foo"]}
      {"assert_latency_ms": {p95_lt: 1800}} → {"kind": "latency_ms", "p95_lt": 1800}
      {"assert_llm_judge": "intent text"}   → {"kind": "llm_judge", "criterion": "intent text"}
      {"assert_tool_called": "name"}        → {"kind": "tool_called", "tool_name": "name"}
      {"assert_tool_args": {...}}           → {"kind": "tool_args", "args": {...}}
      {"assert_language": "es"}             → {"kind": "language", "code": "es"}
      {"kind": "contains", "values": [...]} → passthrough (already normalized)
    """
    if isinstance(entry, str):
        if not entry.startswith(_ASSERT_PREFIX):
            raise ValueError(f"bare assert must start with 'assert_': {entry!r}")
        return {"kind": entry[len(_ASSERT_PREFIX):]}

    if not isinstance(entry, dict) or not entry:
        raise ValueError(f"assert entry must be a non-empty dict or string: {entry!r}")

    # Already-normalized form.
    if "kind" in entry and set(entry.keys()).issubset(
        {"kind", "values", "value", "p95_lt", "p50_lt", "criterion",
         "tool_name", "args", "code"}
    ):
        return dict(entry)

    if len(entry) != 1:
        raise ValueError(
            f"assert dict must have exactly one assert_KIND key (or be normalized): {entry!r}"
        )

    key, value = next(iter(entry.items()))
    if not key.startswith(_ASSERT_PREFIX):
        raise ValueError(f"assert key must start with 'assert_': {key!r}")
    kind = key[len(_ASSERT_PREFIX):]

    if kind in ("contains", "not_contains"):
        if isinstance(value, str):
            return {"kind": kind, "values": [value]}
        if isinstance(value, list):
            return {"kind": kind, "values": value}
        raise ValueError(f"{key} expects a string or list of strings, got {value!r}")
    if kind == "latency_ms":
        if not isinstance(value, dict):
            raise ValueError(f"{key} expects an object like {{p95_lt: 1800}}, got {value!r}")
        return {"kind": kind, **value}
    if kind == "llm_judge":
        return {"kind": kind, "criterion": value}
    if kind == "tool_called":
        return {"kind": kind, "tool_name": value}
    if kind == "tool_args":
        if not isinstance(value, dict):
            raise ValueError(f"{key} expects an object of expected args, got {value!r}")
        return {"kind": kind, "args": value}
    if kind == "language":
        return {"kind": kind, "code": value}
    # generic passthrough — assertion subclass can read whatever it wants.
    if isinstance(value, dict):
        return {"kind": kind, **value}
    return {"kind": kind, "value": value}


def _normalize_asserts(raw: Any) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError(f"asserts must be a list, got {type(raw).__name__}")
    return [_normalize_assert_entry(e) for e in raw]


def _normalize_case(raw: dict[str, Any]) -> dict[str, Any]:
    case = dict(raw)
    case["suite_asserts"] = _normalize_asserts(case.get("suite_asserts"))
    script = case.get("script") or []
    new_script: list[dict[str, Any]] = []
    for turn in script:
        if not isinstance(turn, dict):
            raise ValueError(f"each script entry must be a mapping, got {turn!r}")
        t = dict(turn)
        t["asserts"] = _normalize_asserts(t.get("asserts"))
        new_script.append(t)
    case["script"] = new_script
    return case


def load_suite(
    path: str | Path,
    *,
    env: dict[str, str] | None = None,
    dotenv_path: str | Path | None = None,
) -> EvalSuite:
    """Load and validate a voxeval YAML config."""
    path = Path(path)
    raw_text = path.read_text()
    data = yaml.safe_load(raw_text) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a YAML mapping at top level")

    # Merge env: real os.environ, then .env file (if any), then explicit override.
    merged_env: dict[str, str] = dict(os.environ)
    if dotenv_path is not None:
        merged_env.update(_load_dotenv(Path(dotenv_path)))
    else:
        merged_env.update(_load_dotenv(path.parent / ".env"))
    if env:
        merged_env.update(env)

    data = _expand_env(data, merged_env)

    cases = data.get("cases") or []
    data["cases"] = [_normalize_case(c) for c in cases]

    return EvalSuite.model_validate(data)
