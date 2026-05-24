"""``voxeval run [config.yaml]`` — execute an eval suite."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import typer
from rich.console import Console

from voice_eval_harness.core.budget import BudgetTracker
from voice_eval_harness.core.config import load_suite
from voice_eval_harness.core.engine import lint_preflight, run_suite
from voice_eval_harness.report.json_writer import write_json
from voice_eval_harness.report.junit import write_junit
from voice_eval_harness.report.terminal import render

console = Console()


def run(
    config: Path = typer.Argument(
        Path("voxeval.yaml"),
        help="Path to the voxeval YAML config.",
        exists=True, readable=True, dir_okay=False,
    ),
    concurrency: int = typer.Option(4, "--concurrency", "-c",
                                    help="Max concurrent test cases."),
    verbose: bool = typer.Option(False, "--verbose", "-v",
                                 help="Print full transcripts after the table."),
    junit: Path | None = typer.Option(
        None, "--junit",
        help="Also write a JUnit XML report (CI integration).",
    ),
    json_report: Path | None = typer.Option(
        None, "--json",
        help="Also write a full JSON report (downstream tooling).",
    ),
    max_cost: float | None = typer.Option(
        None, "--max-cost",
        help="Hard ceiling on LLM-judge spend in USD. Assertions over the "
             "ceiling are marked skipped_budget and fail.",
    ),
    skip_lint: bool = typer.Option(
        False, "--skip-lint",
        help="Skip the Retell linter pre-flight even if provider.agent_json is set.",
    ),
    allow_audio: bool = typer.Option(
        False, "--allow-audio",
        help="Permit audio-mode connectors to make real PSTN calls. "
             "Required by Retell audio-mode; bill at provider rates. "
             "Always combine with --max-cost.",
    ),
) -> None:
    import os as _os
    if allow_audio:
        _os.environ["VOXEVAL_ALLOW_AUDIO"] = "1"
    suite = load_suite(config)

    if not skip_lint:
        ok, msgs = lint_preflight(suite)
        for m in msgs:
            console.print(m)
        if not ok:
            console.print(
                "[red bold]Aborting: fix linter fatals before running the suite "
                "(or pass --skip-lint to override).[/red bold]"
            )
            sys.exit(2)

    budget = BudgetTracker(max_cost_usd=max_cost) if max_cost is not None else None
    result = asyncio.run(run_suite(
        suite, concurrency=concurrency, budget=budget,
    ))
    render(result, verbose=verbose)
    if budget is not None:
        console.print(
            f"\nBudget: spent [bold]${budget.spent_usd:.4f}[/bold] of "
            f"${budget.max_cost_usd:.2f} cap; {budget.skipped} call(s) skipped.",
        )
    if junit:
        write_junit(result, junit)
    if json_report:
        write_json(result, json_report)
    sys.exit(0 if result.ok else 1)
