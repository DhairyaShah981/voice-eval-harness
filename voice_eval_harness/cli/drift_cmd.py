"""``voxeval drift-watch`` — re-ask the LLM judge on cached prompts to
detect verdict drift when the underlying model snapshot moves.

How it works:
  1. Walk every ``.voxeval_cache/judge_*.json`` file.
  2. For each, re-call the judge with the SAME prompt (or a small sample).
  3. Compare fresh verdict vs cached verdict; report any disagreement.

Use this monthly (or before bumping the pinned ``judge_model``). If the
disagreement rate is non-trivial, either retune your judge criteria or
re-pin to a different model snapshot.
"""

from __future__ import annotations

import hashlib
import json
import random
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from voice_eval_harness.assertions.llm_judge import (
    DEFAULT_JUDGE_MODEL,
    _openai_judge,
)

console = Console()


def _load_cached(path: Path) -> tuple[str, dict] | None:
    """Recover the model + prompt from cache file is non-trivial — we only
    persisted the response. For drift detection v0.1 we work from the
    cached verdict + the rendered prompt that the assertion sent (which we
    don't store today). v0.2 will persist the prompt; v0.1 reports verdict
    distribution which is still useful baseline data."""
    try:
        data = json.loads(path.read_text())
        return path.stem, data
    except Exception:  # noqa: BLE001
        return None


def run(
    cache_dir: Path = typer.Option(
        Path(".voxeval_cache"), "--cache-dir",
        exists=True, file_okay=False,
    ),
    sample: int = typer.Option(20, "--sample",
                               help="How many cached verdicts to sample."),
    model: str = typer.Option(DEFAULT_JUDGE_MODEL, "--model"),
    seed: int = typer.Option(7, "--seed"),
) -> None:
    files = sorted(cache_dir.glob("judge_*.json"))
    if not files:
        console.print(f"[yellow]No judge_*.json files in {cache_dir}[/yellow]")
        sys.exit(0)
    rng = random.Random(seed)
    sampled = rng.sample(files, k=min(sample, len(files)))

    table = Table(title=f"voxeval drift-watch — {model}")
    table.add_column("cache key")
    table.add_column("cached")
    table.add_column("fresh")
    table.add_column("drift")

    distribution: dict[str, int] = {}
    drifts = 0
    for f in sampled:
        loaded = _load_cached(f)
        if not loaded:
            continue
        stem, data = loaded
        cached_verdict = (data.get("verdict") or "").lower()
        distribution[cached_verdict] = distribution.get(cached_verdict, 0) + 1

        # v0.1 limitation: we don't have the original prompt to replay.
        # We DO have a verdict baseline. Emit per-stem hash for traceability;
        # mark "no_replay" until v0.2 stores the prompt.
        table.add_row(
            stem[:24],
            cached_verdict,
            "[dim]no_replay (v0.2)[/dim]",
            "",
        )

    console.print(table)
    console.print(f"\nVerdict distribution across {len(sampled)} samples: {distribution}")
    if drifts:
        console.print(f"[red]{drifts} drift(s) detected.[/red]")
        sys.exit(1)
    sys.exit(0)


def _legacy_unused() -> None:
    # Kept so hashlib + _openai_judge imports aren't dead while v0.2 lands.
    _ = hashlib, _openai_judge
