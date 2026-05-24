"""``voxeval run [config.yaml]`` — execute an eval suite."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import typer

from voice_eval_harness.core.config import load_suite
from voice_eval_harness.core.engine import run_suite
from voice_eval_harness.report.terminal import render


def run(
    config: Path = typer.Argument(
        Path("voxeval.yaml"),
        help="Path to the voxeval YAML config.",
        exists=True, readable=True, dir_okay=False,
    ),
    concurrency: int = typer.Option(4, "--concurrency", "-c",
                                    help="Max concurrent test cases."),
    verbose: bool = typer.Option(False, "--verbose", "-v",
                                 help="Print full transcripts after the table."),
) -> None:
    suite = load_suite(config)
    result = asyncio.run(run_suite(suite, concurrency=concurrency))
    render(result, verbose=verbose)
    sys.exit(0 if result.ok else 1)
