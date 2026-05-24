"""``voxeval run`` execution engine.

Walks each ``TestCase`` script turn-by-turn against the configured connector,
records the transcript, resolves every assertion, and returns a ``SuiteResult``.
Concurrency is bounded by a semaphore so large suites don't blast a provider.
"""

from __future__ import annotations

import asyncio
import time

from voice_eval_harness.assertions.base import build_assertion
from voice_eval_harness.connectors.base import BaseConnector
from voice_eval_harness.core.models import (
    AssertionResult,
    EvalSuite,
    RunResult,
    SuiteResult,
    TestCase,
)


async def _run_case(connector: BaseConnector, case: TestCase) -> RunResult:
    start = time.monotonic()
    session = await connector.start_session(case)
    error: str | None = None
    try:
        for turn in case.script:
            if turn.user_says is None:
                continue
            await session.send_user_turn(
                turn.user_says,
                lang=turn.language,
                interrupt_at_ms=turn.interrupt_at_ms,
            )
        summary = await session.end()
    except Exception as exc:  # noqa: BLE001 — surface any connector blowup as case failure
        error = f"{type(exc).__name__}: {exc}"
        summary = await session.end() if hasattr(session, "end") else None  # type: ignore[assignment]

    transcript = list(session.transcript)
    assertion_results: list[AssertionResult] = []

    # Per-turn asserts: evaluate against the transcript-so-far at the turn boundary.
    # v0.1 simplification: per-turn asserts see the full transcript at the end.
    all_specs = list(case.suite_asserts)
    for turn in case.script:
        all_specs.extend(turn.asserts)

    if summary is None:
        from voice_eval_harness.core.models import CallSummary
        summary = CallSummary(disconnect_reason="error")

    for spec in all_specs:
        try:
            res = build_assertion(spec).evaluate(transcript, summary)
        except Exception as exc:  # noqa: BLE001
            res = AssertionResult(
                kind=spec.kind, passed=False,
                detail=f"assertion error: {type(exc).__name__}: {exc}",
            )
        assertion_results.append(res)

    passed = error is None and all(r.passed for r in assertion_results)
    duration_ms = int((time.monotonic() - start) * 1000)
    return RunResult(
        case_id=case.id,
        passed=passed,
        duration_ms=duration_ms,
        transcript=transcript,
        assertion_results=assertion_results,
        cost_usd=summary.cost_usd,
        error=error,
    )


async def run_suite(
    suite: EvalSuite,
    *,
    concurrency: int = 4,
    connector: BaseConnector | None = None,
) -> SuiteResult:
    from voice_eval_harness.core.registry import get_connector
    conn = connector or get_connector(suite.provider)
    sem = asyncio.Semaphore(max(1, concurrency))

    async def _bounded(case: TestCase) -> RunResult:
        async with sem:
            return await _run_case(conn, case)

    results = await asyncio.gather(*(_bounded(c) for c in suite.cases))
    total_cost = sum(r.cost_usd for r in results)
    return SuiteResult(cases=results, total_cost_usd=total_cost)
