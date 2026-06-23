"""``voxeval run`` execution engine.

Walks each ``TestCase`` script turn-by-turn against the configured connector,
records the transcript, resolves every assertion, and returns a ``SuiteResult``.

Adds for v0.1.1:
  - Optional `BudgetTracker` ceiling on judge spend (--max-cost).
  - Per-case retries with exponential backoff (read from TestCase.retries).
  - Linter pre-flight when EvalSuite.provider.agent_json is set.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from voice_eval_harness.assertions.base import build_assertion
from voice_eval_harness.connectors.base import BaseConnector
from voice_eval_harness.core.budget import BudgetTracker
from voice_eval_harness.core.models import (
    AssertionResult,
    EvalSuite,
    RunResult,
    SuiteResult,
    TestCase,
)


async def _run_once(connector: BaseConnector, case: TestCase) -> RunResult:
    """One attempt at a case. Returns a RunResult (passed True or False)."""
    start = time.monotonic()
    error: str | None = None
    persona_result = None
    session: object | None = None
    try:
        session = await connector.start_session(case)
    except Exception as exc:  # noqa: BLE001 — connector failure = case failure
        return RunResult(
            case_id=case.id, passed=False,
            duration_ms=int((time.monotonic() - start) * 1000),
            error=f"start_session failed: {type(exc).__name__}: {exc}",
        )
    try:
        if case.persona is not None:
            from dataclasses import replace
            from voice_eval_harness.personas.profiles import get_profile
            from voice_eval_harness.personas.simulator import run_persona
            profile = get_profile(case.persona.type)
            # Merge case-level overrides from YAML (goal, max_turns, params).
            # PersonaProfile is a dataclass; build a kwargs-only override dict
            # so we only touch fields the YAML actually supplied.
            overrides: dict[str, Any] = {}
            p = case.persona.params or {}
            if "goal" in p:
                overrides["goal"] = p["goal"]
            if "max_turns" in p:
                overrides["max_turns"] = int(p["max_turns"])
            # Pass through any other params (lang, accent, etc) merged with builtin defaults.
            merged_params = {**profile.params, **{k: v for k, v in p.items() if k not in {"goal", "max_turns"}}}
            if merged_params:
                overrides["params"] = merged_params
            if overrides:
                profile = replace(profile, **overrides)
            persona_result = await run_persona(session, profile)
        else:
            for turn in case.script:
                if turn.user_says is None:
                    continue
                await session.send_user_turn(
                    turn.user_says,
                    lang=turn.language,
                    interrupt_at_ms=turn.interrupt_at_ms,
                )
        summary = await session.end()
    except Exception as exc:  # noqa: BLE001 — surface any blowup as failure
        error = f"{type(exc).__name__}: {exc}"
        summary = await session.end() if hasattr(session, "end") else None  # type: ignore[assignment]

    transcript = list(session.transcript)
    assertion_results: list[AssertionResult] = []

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
    if persona_result is not None and not persona_result.passed:
        passed = False
        if not error:
            error = f"persona[{case.persona.type}] failed: {persona_result.reason}"  # type: ignore[union-attr]
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


async def _run_case_with_retries(
    connector: BaseConnector, case: TestCase,
) -> RunResult:
    """Wrap _run_once with `case.retries` retries + exp backoff. Marks the
    final result as `flaky` (via assertion detail string) when the case
    passed on some attempts but failed on others."""
    attempts: list[RunResult] = []
    for attempt in range(case.retries + 1):
        res = await _run_once(connector, case)
        attempts.append(res)
        if res.passed:
            break
        if attempt < case.retries:
            await asyncio.sleep(0.5 * (2 ** attempt))

    final = attempts[-1]
    pass_count = sum(1 for a in attempts if a.passed)
    if 0 < pass_count < len(attempts):
        flake_note = (
            f"flaky: passed {pass_count}/{len(attempts)} attempts"
        )
        final.assertion_results.append(AssertionResult(
            kind="meta_flake", passed=final.passed, detail=flake_note,
        ))
    return final


def lint_preflight(suite: EvalSuite) -> tuple[bool, list[str]]:
    """If suite.provider.agent_json points at a real file, run the Retell
    linter against it. Returns (ok, messages)."""
    agent_path = suite.provider.agent_json
    if not agent_path:
        return True, []
    from pathlib import Path
    p = Path(agent_path)
    if not p.exists():
        return True, [f"agent_json {agent_path!r} not found, skipping linter pre-flight"]
    from voice_eval_harness.linters.retell import RETELL_RULES
    from voice_eval_harness.linters.runner import lint_file
    report = lint_file(p, RETELL_RULES)
    if not report.fatals:
        return True, [f"linter pre-flight ✅ ({len(report.warnings)} warning(s))"]
    msgs = [f"linter pre-flight ❌ {len(report.fatals)} fatal(s):"]
    for issue in report.fatals[:10]:
        msgs.append(f"   {issue.render()}")
    return False, msgs


async def run_suite(
    suite: EvalSuite,
    *,
    concurrency: int = 4,
    connector: BaseConnector | None = None,
    budget: BudgetTracker | None = None,
) -> SuiteResult:
    """Run the suite. If ``budget`` is provided, the LLM judge will refuse
    further calls once the spend ceiling is hit (result marked
    ``skipped_budget`` rather than burning past the limit)."""
    from voice_eval_harness.assertions.llm_judge import LLMJudgeAssertion
    from voice_eval_harness.core.registry import get_connector

    conn = connector or get_connector(suite.provider)
    # Thread the budget tracker into the judge assertion class-var. The
    # whole engine runs in one event loop so this is safe for v0.1.
    LLMJudgeAssertion.budget = budget

    sem = asyncio.Semaphore(max(1, concurrency))

    async def _bounded(case: TestCase) -> RunResult:
        async with sem:
            return await _run_case_with_retries(conn, case)

    try:
        results = await asyncio.gather(*(_bounded(c) for c in suite.cases))
    finally:
        LLMJudgeAssertion.budget = None

    total_cost = (budget.spent_usd if budget is not None
                  else sum(r.cost_usd for r in results))

    # Per-persona cost breakdown — only populated if any case has a persona.
    cost_by_persona: dict[str, dict[str, float | int]] = {}
    case_by_id = {c.id: c for c in suite.cases}
    for r in results:
        case = case_by_id.get(r.case_id)
        persona_type = case.persona.type if case and case.persona else None
        if persona_type is None:
            continue
        bucket = cost_by_persona.setdefault(
            persona_type, {"cost_usd": 0.0, "cases": 0, "passed": 0},
        )
        bucket["cost_usd"] = float(bucket["cost_usd"]) + r.cost_usd
        bucket["cases"] = int(bucket["cases"]) + 1
        if r.passed:
            bucket["passed"] = int(bucket["passed"]) + 1

    return SuiteResult(
        cases=results,
        total_cost_usd=total_cost,
        cost_by_persona=cost_by_persona,
    )
