"""``voxeval lint <agent.json>`` — run the Retell structural linter."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from voice_eval_harness.linters.base import Severity
from voice_eval_harness.linters.retell import RETELL_RULES
from voice_eval_harness.linters.runner import lint_file

console = Console()


def run(
    path: Path = typer.Argument(..., exists=True, readable=True, dir_okay=False,
                                help="Path to a Retell agent JSON."),
    fmt: str = typer.Option("text", "--format", "-f",
                            help="Output format: text | json."),
    strict: bool = typer.Option(
        False, "--strict",
        help="Treat warnings as fatal for exit-code purposes.",
    ),
) -> None:
    report = lint_file(path, RETELL_RULES)

    if fmt == "json":
        payload = {
            "path": str(path),
            "rules_run": report.rules_run,
            "fatals": [i.__dict__ for i in report.fatals],
            "warnings": [i.__dict__ for i in report.warnings],
            "ok": report.ok,
        }
        # Severity is an Enum; convert to its string value for JSON.
        for bucket in ("fatals", "warnings"):
            for entry in payload[bucket]:
                if isinstance(entry.get("severity"), Severity):
                    entry["severity"] = entry["severity"].value
        print(json.dumps(payload, indent=2))
        sys.exit(0 if (report.ok and (not strict or not report.warnings)) else 1)

    # Pretty text output.
    if not report.issues:
        console.print(f"✅ [bold green]{path}[/bold green] — "
                      f"all {len(RETELL_RULES)} rules pass.")
        sys.exit(0)

    table = Table(title=f"voxeval lint — {path}", show_lines=False)
    table.add_column("Severity")
    table.add_column("Rule")
    table.add_column("Path")
    table.add_column("Message")
    for issue in report.issues:
        color = {"fatal": "red", "warning": "yellow", "info": "cyan"}[issue.severity.value]
        table.add_row(
            f"[{color}]{issue.severity.value}[/{color}]",
            issue.rule_id,
            issue.path,
            issue.message,
        )
    console.print(table)
    console.print(f"\n{len(report.fatals)} fatal, {len(report.warnings)} warning(s).")
    bad = bool(report.fatals) or (strict and bool(report.warnings))
    sys.exit(1 if bad else 0)
