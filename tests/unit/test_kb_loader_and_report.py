"""KB loader chunks markdown by header; reports write the expected files."""

from __future__ import annotations

import csv
from pathlib import Path

from voice_eval_harness.kb.generator import QaPair
from voice_eval_harness.kb.loader import load_kb, load_kb_glob
from voice_eval_harness.kb.report import (
    QaResult,
    summary,
    write_coverage_csv,
    write_uncovered_md,
)


def _write_sample_kb(tmp_path: Path) -> Path:
    kb = tmp_path / "kb"
    kb.mkdir()
    (kb / "01-providers.md").write_text(
        "# Providers\n\n"
        "## Stockton\n\nDr. Patel sees patients Tuesdays and Thursdays.\n\n"
        "## Bellevue\n\nDr. Smith is available Monday through Friday.\n"
    )
    (kb / "02-insurance.md").write_text(
        "# Insurance\n\nWe accept Blue Shield PPO and Aetna HMO.\n"
    )
    return kb


def test_loader_chunks_by_header(tmp_path: Path) -> None:
    kb = _write_sample_kb(tmp_path)
    chunks = load_kb([kb])
    titles = sorted(c.section for c in chunks)
    assert any("Stockton" in t for t in titles)
    assert any("Bellevue" in t for t in titles)
    assert any("Insurance" in t for t in titles)


def test_loader_glob(tmp_path: Path) -> None:
    _write_sample_kb(tmp_path)
    chunks = load_kb_glob("kb/*.md", base=tmp_path)
    assert len(chunks) >= 3


def test_report_writes_csv_and_md(tmp_path: Path) -> None:
    pairs = [
        QaPair(chunk_id="c1", source="kb/01.md", section="Stockton",
               question="When does Dr. Patel see patients?",
               answer="Tuesdays and Thursdays."),
        QaPair(chunk_id="c2", source="kb/02.md", section="Insurance",
               question="Do you accept Blue Shield PPO?",
               answer="Yes."),
    ]
    results = [
        QaResult(pair=pairs[0], agent_reply="Tuesdays and Thursdays.", covered=True),
        QaResult(pair=pairs[1], agent_reply="I'm not sure.", covered=False),
    ]
    out = tmp_path / "report"
    out.mkdir()
    csv_path = out / "coverage.csv"
    md_path = out / "uncovered.md"
    write_coverage_csv(results, csv_path)
    write_uncovered_md(results, md_path)

    rows = list(csv.reader(csv_path.open()))
    assert rows[0] == ["source", "section", "question", "expected_answer",
                       "agent_reply", "covered"]
    assert len(rows) == 3
    md = md_path.read_text()
    assert "Uncovered KB facts" in md
    assert "Blue Shield PPO" in md

    stats = summary(results)
    assert stats["total"] == 2
    assert stats["covered"] == 1
    assert stats["coverage_rate"] == 0.5
