"""YAML normalization: every assert shorthand turns into a uniform AssertionSpec."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from voice_eval_harness.core.config import _normalize_assert_entry, load_suite


def test_bare_string_assert() -> None:
    out = _normalize_assert_entry("assert_no_crash")
    assert out == {"kind": "no_crash"}


def test_contains_list() -> None:
    out = _normalize_assert_entry({"assert_contains": ["a", "b"]})
    assert out == {"kind": "contains", "values": ["a", "b"]}


def test_contains_string_becomes_list() -> None:
    out = _normalize_assert_entry({"assert_contains": "appointment"})
    assert out == {"kind": "contains", "values": ["appointment"]}


def test_latency_object() -> None:
    out = _normalize_assert_entry({"assert_latency_ms": {"p95_lt": 1800}})
    assert out == {"kind": "latency_ms", "p95_lt": 1800}


def test_tool_called() -> None:
    out = _normalize_assert_entry({"assert_tool_called": "get_slots"})
    assert out == {"kind": "tool_called", "tool_name": "get_slots"}


def test_tool_args() -> None:
    out = _normalize_assert_entry({"assert_tool_args": {"day": "tuesday"}})
    assert out == {"kind": "tool_args", "args": {"day": "tuesday"}}


def test_language_shorthand() -> None:
    out = _normalize_assert_entry({"assert_language": "es"})
    assert out == {"kind": "language", "code": "es"}


def test_invalid_assert_key() -> None:
    with pytest.raises(ValueError, match="must start with 'assert_'"):
        _normalize_assert_entry({"contains": ["x"]})


def test_yaml_env_expansion(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MY_KEY_FOR_TEST", "expanded-value")
    cfg = tmp_path / "voxeval.yaml"
    cfg.write_text(textwrap.dedent("""
        provider:
          name: mock
          api_key: ${MY_KEY_FOR_TEST}
        cases: []
    """).strip())
    suite = load_suite(cfg)
    assert suite.provider.api_key == "expanded-value"
