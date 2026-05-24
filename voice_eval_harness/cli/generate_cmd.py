"""``voxeval generate`` — onboarding-speed test-case generator.

Given an agent JSON (Retell or Vapi) plus optional clinic specifics,
generate a complete voxeval.yaml suite covering:

  - One tool-call case per tool the agent declares (with auto-derived
    ``assert_tool_shape`` from the JSONSchema parameters).
  - 15+ healthcare scenarios (urgent triage, insurance verification,
    new vs. returning patient, prescription refill, after-hours, PHI
    safety, etc.) — see ``scaffold/healthcare_library.py``.
  - 4 persona stress tests (impatient, accented, code-switching, KB-probing).

The generator is template-based and deterministic — no API call required
unless you pass ``--llm-rewrite`` to have gpt-4o tailor the user_says
lines to your clinic's voice.
"""

from __future__ import annotations

import sys
from pathlib import Path

import typer
import yaml
from rich.console import Console

from voice_eval_harness.scaffold.agent_parser import parse_agent
from voice_eval_harness.scaffold.generator import build_suite, write_suite_yaml

console = Console()


def run(
    agent: Path = typer.Option(
        ..., "--agent", "-a",
        exists=True, readable=True, dir_okay=False,
        help="Path to the Retell or Vapi agent JSON.",
    ),
    vertical: str = typer.Option(
        "healthcare", "--vertical",
        help="Scenario library to use. v1.0: healthcare only.",
    ),
    out: Path = typer.Option(
        Path("voxeval.yaml"), "--out", "-o",
        help="Where to write the generated suite.",
    ),
    clinic_config: Path | None = typer.Option(
        None, "--clinic-config",
        help="Optional YAML with clinic-specific substitutions: "
             "patient_name, patient_dob, insurance_plan, specialty, "
             "specialty_indication.",
    ),
    skip_tool_calls: bool = typer.Option(
        False, "--skip-tool-calls",
        help="Skip the auto-derived per-tool happy-path cases.",
    ),
    skip_personas: bool = typer.Option(
        False, "--skip-personas",
        help="Skip the 4 persona-driven cases.",
    ),
    force: bool = typer.Option(
        False, "--force", "-f",
        help="Overwrite the output file if it exists.",
    ),
) -> None:
    if out.exists() and not force:
        console.print(f"[red]{out} already exists. Use --force to overwrite.[/red]")
        sys.exit(2)
    if vertical != "healthcare":
        console.print(
            f"[yellow]vertical={vertical!r} not yet supported. "
            f"v1.0 ships 'healthcare' only.[/yellow]"
        )
        sys.exit(2)

    meta = parse_agent(agent)
    console.print(
        f"\n[bold]Detected agent:[/bold] {meta.agent_name} "
        f"([cyan]{meta.provider}[/cyan])"
    )
    console.print(
        f"  language={meta.language}  "
        f"voice={meta.voice_id or '?'}  "
        f"tools={len(meta.tools)}  "
        f"specialty={meta.detected_specialty or 'unspecified'}  "
        f"kb_wired={meta.has_knowledge_base}"
    )

    clinic_defaults: dict[str, str] = {}
    if clinic_config:
        clinic_defaults = yaml.safe_load(clinic_config.read_text()) or {}
        console.print(
            f"  clinic config: {list(clinic_defaults.keys())}",
        )

    suite = build_suite(
        meta,
        clinic_defaults=clinic_defaults,
        include_tool_calls=not skip_tool_calls,
        include_personas=not skip_personas,
    )
    write_suite_yaml(suite, out)
    n_cases = len(suite["cases"])
    n_tool = sum(1 for c in suite["cases"] if c["id"].startswith("tool_"))
    n_scenario = n_cases - n_tool
    console.print(
        f"\n[bold green]✓ Wrote {out}[/bold green] "
        f"— {n_cases} cases ({n_tool} tool-calls + {n_scenario} scenarios)"
    )
    console.print(
        f"\nNext: replace [bold]REPLACE_WITH_*_AGENT_ID[/bold] in {out}, "
        f"then run [bold]voxeval run {out}[/bold]."
    )
