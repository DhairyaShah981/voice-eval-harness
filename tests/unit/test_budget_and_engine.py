"""Cost guardrail + retries + pre-flight + json_writer."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from voice_eval_harness.assertions.llm_judge import LLMJudgeAssertion
from voice_eval_harness.core.budget import BudgetTracker
from voice_eval_harness.core.engine import lint_preflight, run_suite
from voice_eval_harness.core.models import (
    AssertionSpec,
    EvalSuite,
    ProviderSpec,
    TestCase,
    Turn,
)
from voice_eval_harness.report.json_writer import write_json


def test_budget_tracker_blocks_overspend() -> None:
    async def go() -> None:
        b = BudgetTracker(max_cost_usd=0.001)
        assert await b.try_spend(0.0005)
        assert await b.try_spend(0.0004)
        assert not await b.try_spend(0.0005)
        assert b.skipped == 1
        assert b.remaining_usd is not None
        assert b.remaining_usd < 0.001
    asyncio.run(go())


def test_unlimited_budget_never_blocks() -> None:
    async def go() -> None:
        b = BudgetTracker()
        for _ in range(100):
            assert await b.try_spend(1.0)
        assert b.spent_usd >= 100.0
        assert b.skipped == 0
    asyncio.run(go())


def test_engine_budget_marks_judge_skipped(tmp_path: Path) -> None:
    LLMJudgeAssertion.cache_dir = tmp_path
    calls = {"n": 0}

    def judge(_p: str, _m: str) -> dict:
        calls["n"] += 1
        return {"verdict": "pass", "reason": ""}

    LLMJudgeAssertion.judge_fn = staticmethod(judge)

    # Two cases, each with one judge assertion. Ceiling = 0 USD -> both
    # judge calls must be refused. The default DEFAULT_JUDGE_COST_USD is
    # > 0, so try_spend_sync returns False.
    suite = EvalSuite(
        provider=ProviderSpec(name="mock"),
        cases=[
            TestCase(id=f"c{i}", script=[
                Turn(user_says="hi", asserts=[
                    AssertionSpec(kind="llm_judge", criterion="x"),
                ]),
            ])
            for i in range(2)
        ],
    )
    budget = BudgetTracker(max_cost_usd=0.0)
    result = asyncio.run(run_suite(suite, concurrency=1, budget=budget))
    assert calls["n"] == 0  # ceiling = 0 -> never called
    assert budget.skipped >= 1
    # Every case must have a judge result marked skipped_budget and failing.
    for c in result.cases:
        ar = [a for a in c.assertion_results if a.kind == "llm_judge"]
        assert ar
        assert all(not a.passed for a in ar)
        assert "skipped_budget" in (ar[0].detail or "")


def test_retries_then_pass(tmp_path: Path) -> None:
    """A case with retries=2 should recover from a transient connector
    failure on the second attempt and emit a meta_flake marker.
    (Retries target transient network/connector flakes, not judge verdicts —
    the LLM judge is deterministic and cached.)"""
    from voice_eval_harness.connectors.base import BaseConnector
    from voice_eval_harness.connectors.mock import _MockSession

    state = {"calls": 0}

    class FlakyConnector(BaseConnector):
        name = "flaky"
        supports_audio = False

        async def start_session(self, case):  # type: ignore[override]
            state["calls"] += 1
            if state["calls"] == 1:
                raise RuntimeError("transient network blip")
            return _MockSession(case_id=case.id, scripted_responses=["ok"],
                                scripted_tool_calls=[])

    suite = EvalSuite(
        provider=ProviderSpec(name="mock"),
        cases=[TestCase(id="c1", retries=2, script=[
            Turn(user_says="hi", asserts=[
                AssertionSpec(kind="contains", values=["ok"]),
            ]),
        ])],
    )
    result = asyncio.run(run_suite(
        suite, concurrency=1, connector=FlakyConnector(ProviderSpec(name="flaky")),
    ))
    assert result.cases[0].passed
    assert state["calls"] >= 2
    flake_results = [a for a in result.cases[0].assertion_results
                     if a.kind == "meta_flake"]
    assert flake_results, "expected a meta_flake marker on a flaky pass"


def test_lint_preflight_ok_when_clean_agent(tmp_path: Path) -> None:
    """Clean agent file -> pre-flight returns ok=True."""
    fixture = (Path(__file__).resolve().parents[1]
               / "fixtures" / "agents" / "clean_minimal.json")
    suite = EvalSuite(
        provider=ProviderSpec(
            name="mock", agent_id="x", agent_json=str(fixture),
        ),
    )
    ok, msgs = lint_preflight(suite)
    assert ok
    assert any("pre-flight ✅" in m for m in msgs)


def test_lint_preflight_fails_on_broken(tmp_path: Path) -> None:
    fixture = (Path(__file__).resolve().parents[1] / "fixtures"
               / "agents" / "broken_no_is_transfer_cf.json")
    suite = EvalSuite(
        provider=ProviderSpec(
            name="mock", agent_id="x", agent_json=str(fixture),
        ),
    )
    ok, msgs = lint_preflight(suite)
    assert not ok
    assert any("RTL-004" in m for m in msgs)


def test_lint_preflight_skipped_when_no_agent_json() -> None:
    suite = EvalSuite(provider=ProviderSpec(name="mock"))
    ok, msgs = lint_preflight(suite)
    assert ok
    assert msgs == []


def test_json_writer_round_trips(tmp_path: Path) -> None:
    suite = EvalSuite(provider=ProviderSpec(name="mock"), cases=[
        TestCase(id="c1", script=[Turn(user_says="hi")]),
    ])
    result = asyncio.run(run_suite(suite, concurrency=1))
    out = tmp_path / "report.json"
    write_json(result, out)
    loaded = json.loads(out.read_text())
    assert "cases" in loaded
    assert loaded["cases"][0]["case_id"] == "c1"
