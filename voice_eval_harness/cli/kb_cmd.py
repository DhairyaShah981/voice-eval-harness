"""``voxeval kb-coverage`` — auto-generate Q&A from a markdown KB and verify
the agent can answer them."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import typer
from rich.console import Console

from voice_eval_harness.core.config import load_suite
from voice_eval_harness.core.models import TestCase
from voice_eval_harness.core.registry import get_connector
from voice_eval_harness.kb.generator import build_qa_bank
from voice_eval_harness.kb.loader import load_kb_glob
from voice_eval_harness.kb.matcher import agent_matches_answer
from voice_eval_harness.kb.report import (
    QaResult,
    summary,
    write_coverage_csv,
    write_uncovered_md,
)

console = Console()


async def _run_kb_coverage(
    config_path: Path,
    kb_glob: str,
    out_dir: Path,
    sample_size: int | None,
    min_pass_rate: float,
    skip_verification: bool,
) -> int:
    suite = load_suite(config_path)
    connector = get_connector(suite.provider)

    chunks = load_kb_glob(kb_glob, base=config_path.parent)
    if not chunks:
        console.print(f"[red]No KB chunks found at glob {kb_glob!r}[/red]")
        return 1
    console.print(f"Loaded [bold]{len(chunks)}[/bold] KB chunks "
                  f"from {config_path.parent / kb_glob}")

    qa_bank = build_qa_bank(chunks, skip_verification=skip_verification)
    if sample_size and len(qa_bank) > sample_size:
        qa_bank = qa_bank[:sample_size]
    console.print(f"Generated [bold]{len(qa_bank)}[/bold] verified Q/A pairs")

    results: list[QaResult] = []
    for qa in qa_bank:
        case = TestCase(id=f"kb_{qa.chunk_id}")
        session = await connector.start_session(case)
        try:
            agent_ev = await session.send_user_turn(qa.question)
            reply = agent_ev.text or ""
        except Exception as exc:  # noqa: BLE001
            reply = f"<error: {exc}>"
        finally:
            await session.end()
        covered = bool(reply.strip()) and agent_matches_answer(
            reply, qa.answer, qa.question,
        )
        results.append(QaResult(pair=qa, agent_reply=reply, covered=covered))

    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "coverage.csv"
    md_path = out_dir / "uncovered_facts.md"
    write_coverage_csv(results, csv_path)
    write_uncovered_md(results, md_path)

    stats = summary(results)
    rate = stats["coverage_rate"]
    color = "green" if rate >= min_pass_rate else "red"
    console.print(
        f"\nCoverage: [{color}]{rate:.1%}[/{color}] "
        f"({stats['covered']}/{stats['total']}) — wrote "
        f"[bold]{csv_path}[/bold] and [bold]{md_path}[/bold]"
    )
    return 0 if rate >= min_pass_rate else 1


def run(
    kb: str = typer.Option(..., "--kb", help="Glob for KB markdown files (relative to config dir)."),
    config: Path = typer.Option(
        Path("voxeval.yaml"), "--config",
        exists=True, readable=True, dir_okay=False,
    ),
    out: Path = typer.Option(Path("kb_report"), "--out",
                             help="Output directory for coverage.csv + uncovered_facts.md."),
    sample_size: int | None = typer.Option(None, "--sample-size",
                                              help="Cap on Q/A pairs to evaluate."),
    min_pass_rate: float = typer.Option(0.85, "--min-pass-rate"),
    skip_verification: bool = typer.Option(
        False, "--skip-verification",
        help="Skip the per-pair verification pass (cheaper, less accurate).",
    ),
) -> None:
    code = asyncio.run(_run_kb_coverage(
        config, kb, out, sample_size, min_pass_rate, skip_verification,
    ))
    sys.exit(code)
