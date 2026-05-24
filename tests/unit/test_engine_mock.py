"""End-to-end test: YAML -> engine -> SuiteResult against MockConnector."""

from __future__ import annotations

import asyncio
from pathlib import Path

from voice_eval_harness.core.config import load_suite
from voice_eval_harness.core.engine import run_suite

EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / "mock" / "voxeval.yaml"


def test_mock_example_suite_all_pass() -> None:
    suite = load_suite(EXAMPLE)
    assert len(suite.cases) == 3
    result = asyncio.run(run_suite(suite, concurrency=2))
    failed = [r for r in result.cases if not r.passed]
    assert not failed, (
        "expected all 3 cases to pass; failures:\n" +
        "\n".join(
            f"  {r.case_id}: " + "; ".join(
                f"{a.kind}({a.detail})" for a in r.assertion_results if not a.passed
            )
            for r in failed
        )
    )
    assert result.ok
    assert result.passed == 3
