"""Merge generic healthcare library + analysis.derived_scenarios into a
clinic-specific voxeval.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from voice_eval_harness.analyze.analyzer import ClinicAnalysis
from voice_eval_harness.scaffold.agent_parser import AgentMeta
from voice_eval_harness.scaffold.generator import build_suite, write_suite_yaml


def merge_suite(
    meta: AgentMeta, analysis: ClinicAnalysis,
    *, clinic_defaults: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build the generic suite from agent meta + library, then append the
    LLM-derived clinic-specific scenarios."""
    base = build_suite(meta, clinic_defaults=clinic_defaults)
    existing_ids = {c["id"] for c in base["cases"]}
    # Stamp every derived scenario with a clinic-slug prefix to avoid
    # collisions across multi-clinic directories.
    slug = (meta.agent_name or meta.provider).lower()
    safe = "".join(c if c.isalnum() else "_" for c in slug).strip("_")[:24]
    for s in analysis.derived_scenarios:
        if not isinstance(s, dict):
            continue
        cid_raw = s.get("id") or s.get("name") or "derived"
        cid = f"{safe}__{cid_raw}"
        if cid in existing_ids:
            continue
        s = dict(s)
        s["id"] = cid
        s["description"] = (
            f"[derived from prod transcripts] {s.get('description','')}"
        ).strip()
        s.setdefault("suite_asserts", ["assert_no_crash"])
        base["cases"].append(s)
        existing_ids.add(cid)
    return base


def write_clinic_suite(
    out_dir: Path, meta: AgentMeta, analysis: ClinicAnalysis,
    *, clinic_defaults: dict[str, str] | None = None,
) -> Path:
    """Write voxeval.yaml + analysis.md under ``out_dir``. Returns the yaml path."""
    from voice_eval_harness.analyze.analyzer import render_analysis_md
    out_dir.mkdir(parents=True, exist_ok=True)
    yaml_path = out_dir / "voxeval.yaml"
    suite = merge_suite(meta, analysis, clinic_defaults=clinic_defaults)
    write_suite_yaml(suite, yaml_path)
    (out_dir / "analysis.md").write_text(render_analysis_md(analysis))
    return yaml_path
