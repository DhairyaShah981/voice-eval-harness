"""Coverage matrix output: CSV + uncovered_facts.md."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from voice_eval_harness.kb.generator import QaPair


@dataclass(frozen=True)
class QaResult:
    pair: QaPair
    agent_reply: str
    covered: bool


def write_coverage_csv(results: list[QaResult], path: Path) -> None:
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["source", "section", "question", "expected_answer",
                    "agent_reply", "covered"])
        for r in results:
            w.writerow([
                r.pair.source,
                r.pair.section,
                r.pair.question,
                r.pair.answer,
                r.agent_reply,
                "yes" if r.covered else "no",
            ])


def write_uncovered_md(results: list[QaResult], path: Path) -> None:
    uncovered = [r for r in results if not r.covered]
    lines: list[str] = ["# Uncovered KB facts",
                        f"\n{len(uncovered)} of {len(results)} questions failed.\n"]
    by_source: dict[str, list[QaResult]] = {}
    for r in uncovered:
        by_source.setdefault(r.pair.source, []).append(r)
    for src in sorted(by_source):
        lines.append(f"\n## {src}\n")
        for r in by_source[src]:
            lines.append(f"### {r.pair.section}\n")
            lines.append(f"- **Q:** {r.pair.question}")
            lines.append(f"- **Expected:** {r.pair.answer}")
            lines.append(f"- **Got:** {r.agent_reply or '(no reply)'}\n")
    path.write_text("\n".join(lines))


def summary(results: list[QaResult]) -> dict[str, float | int]:
    total = len(results)
    covered = sum(1 for r in results if r.covered)
    return {
        "total": total,
        "covered": covered,
        "uncovered": total - covered,
        "coverage_rate": (covered / total) if total else 0.0,
    }
