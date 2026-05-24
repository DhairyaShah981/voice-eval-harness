"""Rich terminal renderer for SuiteResult."""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

from voice_eval_harness.core.models import SuiteResult

console = Console()


def render(result: SuiteResult, *, verbose: bool = False) -> None:
    table = Table(title="voxeval run", show_lines=False)
    table.add_column("Case")
    table.add_column("Result")
    table.add_column("Duration")
    table.add_column("Assertions")
    table.add_column("Notes")
    for r in result.cases:
        passed_count = sum(1 for a in r.assertion_results if a.passed)
        total = len(r.assertion_results)
        result_cell = "[green]PASS[/green]" if r.passed else "[red]FAIL[/red]"
        notes = ""
        if r.error:
            notes = f"[red]{r.error}[/red]"
        elif not r.passed:
            fails = [a for a in r.assertion_results if not a.passed]
            notes = "; ".join(f"{a.kind}: {a.detail or 'failed'}" for a in fails[:3])
        table.add_row(
            r.case_id,
            result_cell,
            f"{r.duration_ms}ms",
            f"{passed_count}/{total}",
            notes,
        )
    console.print(table)
    console.print(
        f"\n[bold]{result.passed} passed[/bold], "
        f"[bold]{result.failed} failed[/bold] "
        f"(cost: ${result.total_cost_usd:.4f})"
    )

    if verbose:
        for r in result.cases:
            console.rule(r.case_id)
            for ev in r.transcript:
                console.print(f"  [{ev.role}] {ev.text or ev.tool_name or ''}")
