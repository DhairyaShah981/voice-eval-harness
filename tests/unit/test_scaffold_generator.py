"""voxeval generate — agent JSON → voxeval.yaml scenario generator."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from voice_eval_harness.scaffold.agent_parser import parse_agent
from voice_eval_harness.scaffold.generator import (
    build_suite,
    write_suite_yaml,
)
from voice_eval_harness.scaffold.healthcare_library import render_scenarios

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "agents"


def test_parses_retell_clean_fixture() -> None:
    meta = parse_agent(FIXTURE_DIR / "clean_minimal.json")
    assert meta.provider == "retell"
    assert meta.agent_name == "Minimal Clean Test Agent"
    assert meta.language.startswith("en")
    assert len(meta.tools) == 1
    assert meta.tools[0].name == "check_availability"
    assert "day_of_week" in meta.tools[0].parameters


def test_parses_vapi_assistant_config(tmp_path: Path) -> None:
    cfg = tmp_path / "vapi.json"
    cfg.write_text(json.dumps({
        "name": "test-clinic",
        "model": {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "messages": [{"role": "system",
                          "content": "You are a cardiology scheduler."}],
            "tools": [{
                "type": "function",
                "function": {
                    "name": "lookup_patient",
                    "description": "Look up an existing patient",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "phone": {"type": "string"},
                        },
                        "required": ["phone"],
                    },
                },
            }],
        },
        "transcriber": {"provider": "deepgram", "model": "nova-2",
                        "language": "multi"},
        "voice": {"provider": "11labs", "voiceId": "burt"},
    }))
    meta = parse_agent(cfg)
    assert meta.provider == "vapi"
    assert meta.detected_specialty == "cardiology"
    assert meta.language == "multi"
    assert any(t.name == "lookup_patient" for t in meta.tools)


def test_build_suite_includes_tool_cases_and_scenarios() -> None:
    meta = parse_agent(FIXTURE_DIR / "clean_minimal.json")
    suite = build_suite(meta)
    case_ids = [c["id"] for c in suite["cases"]]
    # Tool-derived: one per declared tool
    assert any(cid.startswith("tool_check_availability") for cid in case_ids)
    # Healthcare scenarios present
    assert "urgent_chest_pain_triage_must_escalate" in case_ids
    assert "wrong_number_no_phi_capture" in case_ids
    # 4 personas (or 3 if monolingual — code_switching is filtered out for en-only agents)
    persona_count = sum(1 for cid in case_ids if cid.startswith("persona_"))
    assert persona_count in (3, 4), f"expected 3 or 4 personas, got {persona_count}"


def test_monolingual_en_agent_drops_spanish_cases() -> None:
    meta = parse_agent(FIXTURE_DIR / "clean_minimal.json")
    suite = build_suite(meta)
    case_ids = [c["id"] for c in suite["cases"]]
    # Clean fixture is en-US only — Spanish drift + code_switching dropped.
    assert "language_drift_spanish" not in case_ids
    assert "persona_code_switching_caller" not in case_ids


def test_clinic_defaults_substitute_into_user_says() -> None:
    rendered = render_scenarios({
        "patient_name": "Alex Ramirez",
        "insurance_plan": "Aetna HMO",
    })
    flat = json.dumps(rendered)
    assert "Alex Ramirez" in flat
    assert "Aetna HMO" in flat


def test_yaml_round_trip(tmp_path: Path) -> None:
    meta = parse_agent(FIXTURE_DIR / "clean_minimal.json")
    suite = build_suite(meta)
    out = tmp_path / "voxeval.yaml"
    write_suite_yaml(suite, out)
    # Must be valid YAML that parses back to a dict with `cases`.
    text = out.read_text()
    body = yaml.safe_load(text)
    assert "cases" in body
    assert body["provider"]["name"] == "retell"
    # Header comments preserved.
    assert text.startswith("# Auto-generated")


def test_yaml_loadable_by_main_engine(tmp_path: Path) -> None:
    """The generated suite must parse cleanly through the main YAML loader."""
    from voice_eval_harness.core.config import load_suite
    meta = parse_agent(FIXTURE_DIR / "clean_minimal.json")
    suite = build_suite(meta)
    out = tmp_path / "voxeval.yaml"
    write_suite_yaml(suite, out)
    eval_suite = load_suite(out)
    assert eval_suite.provider.name == "retell"
    assert len(eval_suite.cases) >= 10
    # Spot-check that a known scenario landed.
    ids = {c.id for c in eval_suite.cases}
    assert "urgent_chest_pain_triage_must_escalate" in ids
