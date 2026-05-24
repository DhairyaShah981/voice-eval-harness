"""``voxeval diff`` — run the same suite against two providers/agents and
report per-case win/loss.

For a team iterating on agent JSONs weekly, this is the killer feature:
"is the new prompt actually better than the old one?" answered without
human eyeballing. The output is a compact table plus a JSON diff payload
suitable for posting as a PR comment.

Two modes:
  - file-vs-file: diff two saved report.json files (no API calls)
  - run-vs-run: run the same suite against TWO providers (or two
    agent_ids), captured in one go.
"""

from __future__ import annotations

import asyncio
import copy
import json
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from voice_eval_harness.core.budget import BudgetTracker
from voice_eval_harness.core.config import load_suite
from voice_eval_harness.core.engine import run_suite
from voice_eval_harness.core.models import SuiteResult

console = Console()


def _load_result(path: Path) -> SuiteResult:
    return SuiteResult.model_validate(json.loads(path.read_text()))


def _diff_table(a: SuiteResult, b: SuiteResult, *, name_a: str, name_b: str) -> None:
    by_id_a = {c.case_id: c for c in a.cases}
    by_id_b = {c.case_id: c for c in b.cases}
    all_ids = sorted(set(by_id_a) | set(by_id_b))

    table = Table(title=f"voxeval diff — {name_a}  vs  {name_b}",
                  show_lines=False)
    table.add_column("Case")
    table.add_column(name_a)
    table.add_column(name_b)
    table.add_column("Delta")

    wins_a = wins_b = ties = regressions = improvements = 0
    for cid in all_ids:
        ca = by_id_a.get(cid)
        cb = by_id_b.get(cid)
        pa = ca.passed if ca else None
        pb = cb.passed if cb else None
        cell_a = ("[green]PASS[/green]" if pa else
                  "[red]FAIL[/red]" if pa is False else "[dim]—[/dim]")
        cell_b = ("[green]PASS[/green]" if pb else
                  "[red]FAIL[/red]" if pb is False else "[dim]—[/dim]")
        if pa and not pb:
            delta = "[red]REGRESSION[/red]"
            regressions += 1
            wins_a += 1
        elif pb and not pa:
            delta = "[green]IMPROVEMENT[/green]"
            improvements += 1
            wins_b += 1
        elif pa == pb:
            delta = ""
            ties += 1
        else:
            delta = "[yellow]NEW[/yellow]"
        table.add_row(cid, cell_a, cell_b, delta)

    console.print(table)
    console.print(
        f"\n[bold]Summary:[/bold] "
        f"{ties} ties, "
        f"[green]{improvements} improvements[/green], "
        f"[red]{regressions} regressions[/red].",
    )
    console.print(
        f"Cost: {name_a}=${a.total_cost_usd:.4f}  "
        f"{name_b}=${b.total_cost_usd:.4f}",
    )


def _write_diff_json(
    a: SuiteResult, b: SuiteResult,
    name_a: str, name_b: str, path: Path,
) -> None:
    by_id_a = {c.case_id: c for c in a.cases}
    by_id_b = {c.case_id: c for c in b.cases}
    rows = []
    for cid in sorted(set(by_id_a) | set(by_id_b)):
        ca = by_id_a.get(cid)
        cb = by_id_b.get(cid)
        rows.append({
            "case_id": cid,
            name_a: {"passed": ca.passed if ca else None,
                     "duration_ms": ca.duration_ms if ca else None,
                     "error": ca.error if ca else None},
            name_b: {"passed": cb.passed if cb else None,
                     "duration_ms": cb.duration_ms if cb else None,
                     "error": cb.error if cb else None},
        })
    path.write_text(json.dumps({
        "left": name_a, "right": name_b,
        "cases": rows,
        "totals": {
            name_a: {"pass": a.passed, "fail": a.failed,
                     "cost_usd": a.total_cost_usd},
            name_b: {"pass": b.passed, "fail": b.failed,
                     "cost_usd": b.total_cost_usd},
        },
    }, indent=2))


def run(
    left: Path = typer.Argument(
        ..., exists=True, readable=True, dir_okay=False,
        help="Either: report.json file (file-vs-file mode), OR voxeval.yaml (run-vs-run mode).",
    ),
    right: Path = typer.Argument(
        ..., exists=True, readable=True, dir_okay=False,
        help="Either: a second report.json, OR a second voxeval.yaml.",
    ),
    name_a: str = typer.Option("A", "--name-a"),
    name_b: str = typer.Option("B", "--name-b"),
    json_out: Path | None = typer.Option(
        None, "--json-out",
        help="Write the structured diff to this path (for PR comments / CI artifact).",
    ),
    concurrency: int = typer.Option(4, "--concurrency", "-c"),
    max_cost: float | None = typer.Option(None, "--max-cost"),
) -> None:
    if left.suffix == ".json" and right.suffix == ".json":
        a = _load_result(left)
        b = _load_result(right)
    else:
        # run-vs-run: load both YAMLs, run them, diff results.
        suite_a = load_suite(left)
        suite_b = load_suite(right)
        budget = (BudgetTracker(max_cost_usd=max_cost)
                  if max_cost is not None else None)
        a, b = asyncio.run(_run_both(suite_a, suite_b, concurrency, budget))

    _diff_table(a, b, name_a=name_a, name_b=name_b)
    if json_out:
        _write_diff_json(a, b, name_a, name_b, json_out)
        console.print(f"\nWrote diff -> {json_out}")

    # Exit non-zero if there are regressions (good for CI).
    by_id_a = {c.case_id: c for c in a.cases}
    by_id_b = {c.case_id: c for c in b.cases}
    regressions = sum(
        1 for cid in by_id_a
        if by_id_a[cid].passed
        and cid in by_id_b
        and not by_id_b[cid].passed
    )
    sys.exit(1 if regressions else 0)


async def _run_both(suite_a, suite_b, concurrency, budget):
    # If suites share a provider config but want different agent_ids,
    # caller already encoded that in the YAML. Just run them sequentially
    # so we don't double-bill concurrency.
    ra = await run_suite(suite_a, concurrency=concurrency, budget=budget)
    # Reset the budget tracker between runs to give B a fair shot.
    if budget is not None:
        budget_b = copy.copy(budget)
        budget_b.spent_usd = 0.0
        budget_b.skipped = 0
        rb = await run_suite(suite_b, concurrency=concurrency, budget=budget_b)
    else:
        rb = await run_suite(suite_b, concurrency=concurrency)
    return ra, rb
