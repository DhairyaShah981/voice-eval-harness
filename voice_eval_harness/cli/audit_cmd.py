"""``voxeval audit`` — score the last N production calls against a YAML
suite of suite-level assertions.

Pulls every call from Retell `/v3/list-calls` since the given window, parses
its transcript, runs your suite_asserts (e.g. assert_pii_redacted,
assert_no_crash, assert_not_contains failure-signatures) against the recorded
events. No live calls made; no API cost beyond list-calls.

The companion to ``voxeval replay``: replay generates regression fixtures;
audit answers "did the last 24 hours of real calls pass our quality bar?"
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from voice_eval_harness.assertions.base import build_assertion
from voice_eval_harness.core.config import load_suite
from voice_eval_harness.core.models import (
    AssertionResult,
    CallSummary,
    Role,
    TranscriptEvent,
)
from voice_eval_harness.replay.extractor import parse_transcript
from voice_eval_harness.replay.retell_source import list_failed_calls

console = Console()


async def _score_one(call: dict, suite_asserts: list) -> list[AssertionResult]:
    transcript: list[TranscriptEvent] = []
    for i, (role, text) in enumerate(parse_transcript(call.get("transcript") or "")):
        try:
            role_enum = Role(role)
        except ValueError:
            role_enum = Role.SYSTEM
        transcript.append(TranscriptEvent(ts_ms=i, role=role_enum, text=text))
    summary = CallSummary(
        disconnect_reason=call.get("disconnection_reason"),
        tool_invocations=call.get("tool_calls") or [],
    )
    results: list[AssertionResult] = []
    for spec in suite_asserts:
        try:
            res = build_assertion(spec).evaluate(transcript, summary)
        except Exception as exc:  # noqa: BLE001
            res = AssertionResult(
                kind=spec.kind, passed=False,
                detail=f"assertion error: {type(exc).__name__}: {exc}",
            )
        results.append(res)
    return results


async def _run(
    config: Path, since: str, statuses: list[str] | None, max_calls: int,
) -> int:
    suite = load_suite(config)
    # The auditor only uses suite-level asserts (case-level scripts don't
    # apply to passive prod calls).
    suite_asserts = []
    for c in suite.cases:
        suite_asserts.extend(c.suite_asserts)
    if not suite_asserts:
        console.print("[yellow]No suite_asserts found in any case — nothing to audit.[/yellow]")
        return 1

    console.print(f"Pulling calls (since={since}, statuses={statuses or 'all'}) from Retell...")
    # statuses=[] -> no disconnection_reason filter, pull every call in window.
    calls = await list_failed_calls(
        since=since, statuses=statuses or [], limit=max_calls,
    )
    console.print(f"  -> got {len(calls)} call(s)")

    table = Table(title=f"voxeval audit ({since}, {len(calls)} calls)")
    table.add_column("call_id")
    table.add_column("disconnect")
    table.add_column("asserts (pass/total)")
    table.add_column("first failure")

    failed_calls = 0
    for call in calls:
        results = await _score_one(call, suite_asserts)
        passes = sum(1 for r in results if r.passed)
        first_fail = next((r for r in results if not r.passed), None)
        ok = (first_fail is None)
        if not ok:
            failed_calls += 1
        color = "green" if ok else "red"
        table.add_row(
            call.get("call_id", "?")[:24],
            call.get("disconnection_reason", "?"),
            f"[{color}]{passes}/{len(results)}[/{color}]",
            (f"{first_fail.kind}: {first_fail.detail[:60]}"
             if first_fail else ""),
        )

    console.print(table)
    console.print(
        f"\n[bold]{len(calls) - failed_calls} of {len(calls)} calls passed[/bold] "
        f"all suite_asserts."
    )
    return 0 if failed_calls == 0 else 1


def run(
    config: Path = typer.Option(
        Path("voxeval.yaml"), "--config",
        exists=True, readable=True, dir_okay=False,
    ),
    since: str = typer.Option("24h", "--since"),
    status: list[str] = typer.Option([], "--status",
                                     help="Filter on disconnection_reason (repeatable)."),
    max_calls: int = typer.Option(50, "--max-calls"),
) -> None:
    code = asyncio.run(_run(config, since, status or None, max_calls))
    sys.exit(code)
