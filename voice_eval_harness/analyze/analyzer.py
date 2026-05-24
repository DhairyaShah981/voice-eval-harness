"""Per-clinic analyzer: corpus + KB + LLM client -> structured analysis JSON."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from voice_eval_harness.analyze.corpus import ClinicCorpus, stratified_sample
from voice_eval_harness.analyze.llm_client import AnalyzeClient, AnalyzeResponse
from voice_eval_harness.analyze.prompts import (
    SYSTEM_PROMPT,
    assemble_corpus_text,
    render_user_prompt,
)


@dataclass
class ClinicAnalysis:
    agent_id: str
    agent_name: str | None
    specialty: str | None
    summary: str = ""
    happy_paths: list[dict[str, Any]] = field(default_factory=list)
    failure_modes: list[dict[str, Any]] = field(default_factory=list)
    derived_scenarios: list[dict[str, Any]] = field(default_factory=list)
    kb_coverage_gaps: list[str] = field(default_factory=list)
    recommended_tool_shapes: list[dict[str, Any]] = field(default_factory=list)
    llm_response: AnalyzeResponse | None = None


def _load_kb(kb_dir: Path | None) -> str:
    if kb_dir is None or not kb_dir.exists():
        return ""
    parts: list[str] = []
    for md in sorted(kb_dir.rglob("*.md")):
        try:
            parts.append(f"\n--- {md.name} ---\n" + md.read_text())
        except Exception:  # noqa: BLE001
            continue
    return "\n".join(parts)[:30_000]


def analyze_clinic(
    corpus: ClinicCorpus,
    client: AnalyzeClient,
    *,
    kb_dir: Path | None = None,
    specialty: str | None = None,
    max_calls: int = 40,
) -> ClinicAnalysis:
    sample = stratified_sample(corpus, max_calls=max_calls)
    corpus_text = assemble_corpus_text(sample)
    kb_text = _load_kb(kb_dir)
    user_prompt = render_user_prompt(
        agent_id=corpus.agent_id,
        agent_name=corpus.agent_name,
        specialty=specialty,
        n_calls=len(sample),
        n_total=len(corpus.calls),
        corpus_text=corpus_text,
        kb_text=kb_text,
    )
    # haiku/sonnet 4.5+ both support 16K+ output. Cap generously so the
    # structured JSON (which can grow with many derived_scenarios) is
    # never truncated mid-array.
    data = client.generate_json(
        system=SYSTEM_PROMPT, user=user_prompt, max_tokens=16000,
    )
    return ClinicAnalysis(
        agent_id=corpus.agent_id,
        agent_name=corpus.agent_name,
        specialty=specialty,
        summary=data.get("summary", ""),
        happy_paths=data.get("happy_paths", []) or [],
        failure_modes=data.get("failure_modes", []) or [],
        derived_scenarios=data.get("derived_scenarios", []) or [],
        kb_coverage_gaps=data.get("kb_coverage_gaps", []) or [],
        recommended_tool_shapes=data.get("recommended_tool_shapes", []) or [],
    )


def render_analysis_md(analysis: ClinicAnalysis) -> str:
    """Render a human-readable narrative of what the analyzer found."""
    lines: list[str] = [
        f"# {analysis.agent_name or analysis.agent_id}",
        f"\n_agent_id_: `{analysis.agent_id}`",
        f"_specialty_: {analysis.specialty or 'unspecified'}\n",
        "## Summary\n",
        analysis.summary or "(no summary returned)",
        "\n## Happy paths observed\n",
    ]
    for p in analysis.happy_paths:
        lines.append(f"### {p.get('name','<unnamed>')} — _freq {p.get('frequency','?')}_")
        lines.append(p.get("description", ""))
        for ex in (p.get("user_says_examples") or [])[:3]:
            lines.append(f"  - `\"{ex}\"`")
        if p.get("expected_tool_calls"):
            lines.append(f"  - tool calls: {', '.join(p['expected_tool_calls'])}")
        lines.append("")

    lines.append("## Failure modes observed\n")
    for f in analysis.failure_modes:
        lines.append(f"### {f.get('name','<unnamed>')} — _{f.get('occurred_in_calls','?')} call(s)_")
        lines.append(f.get("description", ""))
        lines.append(f"- **Pattern**: {f.get('agent_failure_pattern','?')}")
        for ex in (f.get("user_says_examples") or [])[:2]:
            lines.append(f"  - `\"{ex}\"`")
        lines.append("")

    if analysis.kb_coverage_gaps:
        lines.append("## KB coverage gaps\n")
        for g in analysis.kb_coverage_gaps:
            lines.append(f"- {g}")
        lines.append("")

    if analysis.recommended_tool_shapes:
        lines.append("## Recommended tool-shape contracts\n")
        for t in analysis.recommended_tool_shapes:
            lines.append(f"### `{t.get('tool_name','?')}`")
            for s in t.get("suggested_assertions", []):
                lines.append(f"- {s}")
            lines.append("")

    lines.append(f"## Derived scenarios ({len(analysis.derived_scenarios)})\n")
    lines.append("See `voxeval.yaml` (merged with the generic healthcare library) for the runnable suite.")
    return "\n".join(lines)
