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
from voice_eval_harness.cli import init_cmd, kb_cmd, lint_cmd, run_cmd  # noqa: E402

app.command("init", help="Scaffold a new voxeval project in the current directory.")(init_cmd.run)
app.command("lint", help="Run the Retell structural linter on an agent JSON file.")(lint_cmd.run)
app.command("run", help="Run a voxeval suite against the configured provider.")(run_cmd.run)
app.command("kb-coverage", help="Generate Q&A from a markdown KB and verify the agent answers them.")(kb_cmd.run)


if __name__ == "__main__":
    app()
