"""voxeval — CLI entry point.

Built with Typer. Each sub-command lives in its own module under
``voice_eval_harness.cli`` and registers itself onto ``app`` below.
"""

from __future__ import annotations

import typer
from rich.console import Console

from voice_eval_harness import __version__

console = Console()
app = typer.Typer(
    name="voxeval",
    help="Open-source eval harness for voice AI agents (Retell, Vapi, LiveKit, Pipecat).",
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="rich",
)


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"voxeval [bold cyan]{__version__}[/bold cyan]")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        callback=_version_callback,
        is_eager=True,
        help="Show the version and exit.",
    ),
) -> None:
    """Voice AI eval harness."""


# Sub-commands are registered here as they land. Each command lives in its
# own module to keep this file thin and to keep import cost low.
from voice_eval_harness.cli import (  # noqa: E402
    audit_cmd,
    diff_cmd,
    drift_cmd,
    generate_cmd,
    init_cmd,
    kb_cmd,
    lint_cmd,
    pin_urls_cmd,
    replay_cmd,
    run_cmd,
)

app.command("init", help="Scaffold a new voxeval project in the current directory.")(init_cmd.run)
app.command("generate", help="Auto-generate a healthcare voxeval suite from an agent JSON (Retell or Vapi).")(generate_cmd.run)
app.command("lint", help="Run the Retell structural linter on an agent JSON file.")(lint_cmd.run)
app.command("run", help="Run a voxeval suite against the configured provider.")(run_cmd.run)
app.command("diff", help="Diff two suite runs (or two voxeval.yaml configs) and surface per-case regressions / improvements.")(diff_cmd.run)
app.command("kb-coverage", help="Generate Q&A from a markdown KB and verify the agent answers them.")(kb_cmd.run)
app.command("replay", help="Generate regression fixtures from real prod call failures.")(replay_cmd.run)
app.command("pin-urls", help="Probe every tool/webhook URL in an agent JSON; fails if any are unreachable.")(pin_urls_cmd.run)
app.command("audit", help="Score the last N production calls against a YAML suite of assertions.")(audit_cmd.run)
app.command("drift-watch", help="Re-check cached LLM-judge verdicts for drift across model snapshots.")(drift_cmd.run)


if __name__ == "__main__":
    app()
