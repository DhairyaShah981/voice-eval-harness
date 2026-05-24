"""``voxeval init`` — scaffold a new project in the current directory.

Creates ``voxeval.yaml``, ``.env.example``, an ``agents/`` placeholder,
and a single example test case so the user has something to point
``voxeval run`` at immediately.
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

console = Console()

_SAMPLE_YAML = """\
# voxeval.yaml — scaffolded by `voxeval init`.
# See https://github.com/DhairyaShah981/voice-eval-harness for full grammar.

provider:
  name: {provider}
  api_key: ${{{key_env}}}
  agent_id: REPLACE_WITH_YOUR_AGENT_ID
  # Optional: path to the agent JSON for pre-flight lint.
  # agent_json: ./agents/my-agent.json

defaults:
  mode: text
  timeout_s: 45
  judge_model: gpt-4o-mini-2024-07-18

cases:
  - id: greeting_smoke
    description: Agent greets and offers help on first turn.
    script:
      - user_says: "Hello"
        asserts:
          - assert_llm_judge: "agent greets the caller and offers assistance"
          - assert_no_crash
"""

_SAMPLE_ENV = """\
# Fill in the keys you actually use. Add this file to .gitignore.
RETELL_API_KEY=
VAPI_API_KEY=
OPENAI_API_KEY=
"""


def run(
    provider: str = typer.Option(
        "retell",
        "--provider",
        "-p",
        help="Which provider to scaffold for (retell, vapi).",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Overwrite existing files.",
    ),
) -> None:
    cwd = Path.cwd()
    key_env = {"retell": "RETELL_API_KEY", "vapi": "VAPI_API_KEY"}.get(
        provider.lower(), "RETELL_API_KEY"
    )

    targets = {
        cwd / "voxeval.yaml": _SAMPLE_YAML.format(provider=provider.lower(), key_env=key_env),
        cwd / ".env.example": _SAMPLE_ENV,
    }
    agents_dir = cwd / "agents"
    agents_dir.mkdir(exist_ok=True)

    created: list[Path] = []
    skipped: list[Path] = []
    for path, content in targets.items():
        if path.exists() and not force:
            skipped.append(path)
            continue
        path.write_text(content)
        created.append(path)

    for path in created:
        console.print(f"  [green]+[/green] {path.relative_to(cwd)}")
    for path in skipped:
        console.print(f"  [yellow]~[/yellow] {path.relative_to(cwd)} (exists, use --force)")
    console.print(
        f"\nScaffolded for [bold cyan]{provider}[/bold cyan]. "
        f"Edit [bold]voxeval.yaml[/bold] and run [bold]voxeval run[/bold]."
    )
