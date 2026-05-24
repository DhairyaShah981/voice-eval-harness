"""``voxeval analyze`` — historical transcripts → clinic-specific test suites.

Pulls a window of Retell calls, groups them by ``agent_id`` (= clinic),
PHI-scrubs the transcripts, sends each clinic's corpus + KB markdown to
the configured analyzer LLM (default: Vertex Claude under your BAA),
and writes a ``clinic_suites/{slug}/`` directory per clinic with:

  voxeval.yaml   — merged generic library + LLM-derived scenarios
  analysis.md    — human-readable narrative of what the LLM saw
  transcripts/   — the (scrubbed) corpus the analyzer consumed

Run this monthly on production traffic to keep clinic-specific regression
suites grounded in real call patterns rather than imagined ones.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from voice_eval_harness.analyze.analyzer import analyze_clinic
from voice_eval_harness.analyze.corpus import (
    group_and_scrub,
    write_corpus_to_disk,
)
from voice_eval_harness.analyze.llm_client import get_analyze_client
from voice_eval_harness.analyze.synthesizer import write_clinic_suite
from voice_eval_harness.replay.retell_source import list_failed_calls
from voice_eval_harness.scaffold.agent_parser import parse_agent

console = Console()


async def _pull_all_calls(
    since: str, max_calls: int,
) -> list[dict]:
    """Pull the broadest possible window — pass statuses=[] (empty list)
    so list_failed_calls omits the disconnection_reason filter entirely.
    Analyzer needs happy + failure calls together to derive scenarios."""
    return await list_failed_calls(
        since=since, statuses=[], limit=max_calls,
    )


def run(
    out: Path = typer.Option(
        Path("clinic_suites"), "--out",
        help="Root directory for the per-clinic outputs.",
    ),
    since: str = typer.Option(
        "30d", "--since",
        help="Window to pull from Retell (e.g. 7d / 30d / 90d).",
    ),
    max_calls: int = typer.Option(
        200, "--max-calls",
        help="Cap on total calls pulled from Retell.",
    ),
    sample_per_clinic: int = typer.Option(
        40, "--sample-per-clinic",
        help="Cap on calls per clinic sent to the analyzer LLM.",
    ),
    backend: str | None = typer.Option(
        None, "--backend",
        help="LLM backend: vertex (recommended, BAA) | anthropic | openai. "
             "Falls back to VOXEVAL_ANALYZE_BACKEND env var, then auto-pick.",
    ),
    vertex_project: str | None = typer.Option(
        None, "--vertex-project", envvar="VOXEVAL_VERTEX_PROJECT",
        help="GCP project for Vertex Claude (BAA-covered).",
    ),
    vertex_location: str = typer.Option(
        "us-east5", "--vertex-location",
        help="GCP region for Vertex (us-east5 has widest Claude coverage; "
             "us-central1 may NOT have Anthropic models enabled).",
    ),
    vertex_model: str = typer.Option(
        "claude-haiku-4-5@20251001", "--vertex-model",
        help="Default matches the trifetch-os backend; switch to "
             "claude-sonnet-4-6 for richer derived scenarios at higher cost.",
    ),
    transcripts_file: Path | None = typer.Option(
        None, "--transcripts-file",
        help="Skip Retell pull; load calls from a JSON file (testing).",
    ),
    agents_index_file: Path | None = typer.Option(
        None, "--agents-index-file",
        help="Optional JSON mapping {agent_id: {name, agent_json_path, "
             "kb_dir}} for richer per-clinic context.",
    ),
    max_cost: float = typer.Option(
        5.0, "--max-cost",
        help="Hard ceiling on analyzer LLM spend in USD across all clinics.",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run",
        help="Pull and scrub only; skip the LLM call. Useful for inspecting "
             "the corpus before paying for analysis.",
    ),
    use_presidio: bool = typer.Option(
        False, "--use-presidio",
        help="Use Microsoft Presidio NER on top of regex PHI scrubbing "
             "(requires the [phi] extra).",
    ),
) -> None:
    # 1. Pull (or load) calls
    if transcripts_file:
        calls = json.loads(transcripts_file.read_text())
        console.print(f"Loaded [bold]{len(calls)}[/bold] calls from "
                      f"{transcripts_file}")
    else:
        console.print(f"Pulling up to {max_calls} calls from Retell "
                      f"since {since}...")
        calls = asyncio.run(_pull_all_calls(since, max_calls))
        console.print(f"  -> got {len(calls)} call(s)")

    if not calls:
        console.print("[yellow]No calls returned — nothing to analyze.[/yellow]")
        sys.exit(1)

    # 2. Optional agents-index for richer per-clinic metadata
    agents_index: dict[str, dict] = {}
    if agents_index_file:
        agents_index = json.loads(agents_index_file.read_text())

    # 3. Group + scrub
    name_lookup = {aid: meta.get("name") for aid, meta in agents_index.items()}
    corpora = group_and_scrub(calls, agent_name_lookup=name_lookup,
                              use_presidio=use_presidio)
    console.print(f"Grouped into [bold]{len(corpora)}[/bold] clinic(s) "
                  f"after PHI scrubbing.")

    # 4. Build LLM client (skip if dry-run)
    client = None
    if not dry_run:
        client = get_analyze_client(
            backend=backend,
            vertex_project=vertex_project,
            vertex_location=vertex_location,
            vertex_model=vertex_model,
        )
        console.print(f"Analyzer backend: [bold]{client.backend_name}[/bold]")

    # 5. Per-clinic pass
    out.mkdir(parents=True, exist_ok=True)
    table = Table(title=f"voxeval analyze — {len(corpora)} clinics, "
                        f"window {since}")
    table.add_column("clinic")
    table.add_column("calls")
    table.add_column("happy/fail")
    table.add_column("derived")
    table.add_column("cost")

    total_cost = 0.0
    for agent_id, corpus in corpora.items():
        clinic_meta = agents_index.get(agent_id, {})
        agent_name = corpus.agent_name or clinic_meta.get("name") or agent_id
        clinic_dir = out / corpus.slug

        sample = corpus.calls  # write all by default; analyzer re-samples internally
        stats = write_corpus_to_disk(corpus, clinic_dir, sample=sample)

        n_derived = 0
        analyzer_cost = 0.0

        if dry_run or client is None:
            console.print(f"  [dim]{corpus.slug}: dry-run — wrote "
                          f"{stats['transcripts_written']} transcripts[/dim]")
        else:
            if total_cost >= max_cost:
                console.print(f"  [yellow]{corpus.slug}: skipped — "
                              f"--max-cost {max_cost} reached[/yellow]")
                table.add_row(corpus.slug, str(len(corpus.calls)),
                              f"{len(corpus.happy_calls)}/{len(corpus.failed_calls)}",
                              "skipped", f"${total_cost:.2f}")
                continue
            specialty = None
            agent_json = clinic_meta.get("agent_json_path")
            agent_meta_obj = None
            if agent_json:
                try:
                    agent_meta_obj = parse_agent(Path(agent_json))
                    specialty = agent_meta_obj.detected_specialty
                except Exception as exc:  # noqa: BLE001
                    console.print(f"  [yellow]failed to parse {agent_json}: "
                                  f"{exc}[/yellow]")

            kb_dir = clinic_meta.get("kb_dir")
            try:
                analysis = analyze_clinic(
                    corpus, client,
                    kb_dir=Path(kb_dir) if kb_dir else None,
                    specialty=specialty,
                    max_calls=sample_per_clinic,
                )
            except Exception as exc:  # noqa: BLE001
                console.print(f"  [red]{corpus.slug}: analyzer failed — "
                              f"{type(exc).__name__}: {exc}[/red]")
                table.add_row(corpus.slug, str(len(corpus.calls)),
                              f"{len(corpus.happy_calls)}/{len(corpus.failed_calls)}",
                              "ERR", "—")
                continue
            n_derived = len(analysis.derived_scenarios)
            if analysis.llm_response:
                analyzer_cost = analysis.llm_response.cost_usd
            total_cost += analyzer_cost

            if agent_meta_obj is None:
                # Fall back: synthesize a minimal AgentMeta from the corpus.
                from voice_eval_harness.scaffold.agent_parser import AgentMeta
                agent_meta_obj = AgentMeta(
                    provider="retell", agent_name=agent_name,
                    language="en-US", languages_supported=["en"],
                    voice_id=None, global_prompt="", node_names=[],
                    tools=[], knowledge_base_ids=[], has_knowledge_base=False,
                    references_kb_in_prompt=False, detected_specialty=specialty,
                )

            yaml_path = write_clinic_suite(clinic_dir, agent_meta_obj, analysis)
            console.print(f"  [green]{corpus.slug}: wrote "
                          f"{yaml_path.relative_to(out)} "
                          f"({n_derived} derived scenarios)[/green]")

        table.add_row(
            corpus.slug, str(len(corpus.calls)),
            f"{len(corpus.happy_calls)}/{len(corpus.failed_calls)}",
            str(n_derived), f"${analyzer_cost:.4f}",
        )

    console.print(table)
    console.print(f"\n[bold]Total analyzer spend: ${total_cost:.4f}[/bold] "
                  f"(cap was ${max_cost:.2f})")
    sys.exit(0)
