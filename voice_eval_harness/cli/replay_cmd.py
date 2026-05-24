"""``voxeval replay`` — generate regression fixtures from real prod failures."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import typer
import yaml
from rich.console import Console

from voice_eval_harness.replay.extractor import (
    extract_fixture,
    fixture_to_yaml_dict,
)
from voice_eval_harness.replay.retell_source import list_failed_calls

console = Console()


async def _run_replay(
    provider: str,
    since: str,
    statuses: list[str],
    max_cases: int,
    out_dir: Path,
    write_aggregated: bool,
) -> int:
    if provider != "retell":
        console.print(f"[yellow]provider {provider!r} replay not yet implemented; "
                      f"only 'retell' is supported in v0.1.[/yellow]")
        return 1

    console.print(f"Pulling failed calls (since={since}, statuses={statuses}) "
                  f"from Retell...")
    calls = await list_failed_calls(
        since=since, statuses=statuses, limit=max_cases,
    )
    console.print(f"  -> got {len(calls)} call(s)")

    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    seen_case_ids: set[str] = set()
    aggregated: list[dict] = []
    for call in calls:
        fix = extract_fixture(call)
        if fix is None or fix.case_id in seen_case_ids:
            continue
        seen_case_ids.add(fix.case_id)
        case_dict = fixture_to_yaml_dict(fix)
        path = out_dir / f"{fix.case_id}.yaml"
        path.write_text(yaml.safe_dump(case_dict, sort_keys=False))
        written.append(fix.case_id)
        aggregated.append(case_dict)
        red = sum(fix.raw_redactions.values())
        console.print(f"  + {path.name}  (redactions={red})")

    if write_aggregated and aggregated:
        bundle = out_dir / "replay-bundle.yaml"
        bundle.write_text(yaml.safe_dump(
            {"cases": aggregated}, sort_keys=False,
        ))
        console.print(f"\nBundled {len(aggregated)} cases into {bundle}")

    console.print(f"\n[bold]Wrote {len(written)} deduped fixture(s)[/bold] to "
                  f"{out_dir.resolve()}")
    return 0


def run(
    provider: str = typer.Option("retell", "--provider",
                                 help="Which provider to replay from (v0.1: retell)."),
    since: str = typer.Option("7d", "--since",
                              help="How far back to look (e.g. 7d, 24h, 30m)."),
    statuses: list[str] = typer.Option(
        ["agent_error", "dial_busy", "error_user_not_joined"],
        "--status",
        help="Disconnection reasons to pull (repeatable).",
    ),
    max_cases: int = typer.Option(25, "--max-cases"),
    out: Path = typer.Option(Path("replay_cases"), "--out",
                             help="Directory to write fixture YAMLs into."),
    bundle: bool = typer.Option(True, "--bundle/--no-bundle",
                                help="Also write a single replay-bundle.yaml with all cases."),
) -> None:
    code = asyncio.run(_run_replay(provider, since, statuses, max_cases, out, bundle))
    sys.exit(code)
