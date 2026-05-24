"""voxeval analyze pipeline: corpus loading, stratified sampling, scrubbing,
synthesizer merging, end-to-end clinic-suite writing."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from voice_eval_harness.analyze.analyzer import (
    ClinicAnalysis,
    analyze_clinic,
    render_analysis_md,
)
from voice_eval_harness.analyze.corpus import (
    group_and_scrub,
    stratified_sample,
    write_corpus_to_disk,
)
from voice_eval_harness.analyze.llm_client import AnalyzeClient, AnalyzeResponse
from voice_eval_harness.analyze.synthesizer import merge_suite, write_clinic_suite
from voice_eval_harness.scaffold.agent_parser import AgentMeta


class _StubClient(AnalyzeClient):
    backend_name = "stub"

    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls = 0

    def generate(self, *, system: str, user: str, max_tokens: int = 4096) -> AnalyzeResponse:
        self.calls += 1
        return AnalyzeResponse(text=json.dumps(self.payload),
                                input_tokens=1000, output_tokens=400,
                                cost_usd=0.045)


def _raw_calls() -> list[dict]:
    return [
        {"call_id": "c1", "agent_id": "agent_ent_eva",
         "transcript": "User: my phone is (415) 555-2671\nAgent: Sure, "
                       "when would you like the appointment?",
         "disconnection_reason": "user_hangup", "duration_ms": 95000,
         "start_timestamp": 1_000_000},
        {"call_id": "c2", "agent_id": "agent_ent_eva",
         "transcript": "User: I'm having chest pain.\nAgent: appointment "
                       "available next Tuesday at 2pm.",
         "disconnection_reason": "agent_error", "duration_ms": 30000,
         "start_timestamp": 1_000_500},
        {"call_id": "c3", "agent_id": "agent_cardio_iris",
         "transcript": "User: I need to refill my BP meds.\nAgent: I can "
                       "schedule that for you.",
         "disconnection_reason": "user_hangup", "duration_ms": 60000,
         "start_timestamp": 1_001_000},
        {"call_id": "c4", "agent_id": "agent_ent_eva",
         "transcript": "User: hello\nAgent: Hi, how can I help?",
         "disconnection_reason": "user_hangup", "duration_ms": 80000,
         "start_timestamp": 1_001_500},
    ]


def test_group_and_scrub_phi_redacted() -> None:
    corpora = group_and_scrub(_raw_calls())
    assert set(corpora.keys()) == {"agent_ent_eva", "agent_cardio_iris"}
    eva = corpora["agent_ent_eva"]
    # PHI scrubber must have replaced the phone number.
    assert any("<redacted:phone>" in c.transcript for c in eva.calls)
    assert not any("555-2671" in c.transcript for c in eva.calls)


def test_stratified_sample_includes_failures() -> None:
    corpora = group_and_scrub(_raw_calls())
    eva = corpora["agent_ent_eva"]
    sample = stratified_sample(eva, max_calls=4)
    # Sample size respects bound and contains the agent_error call.
    assert len(sample) <= 4
    assert any(c.disconnect_reason == "agent_error" for c in sample)


def test_write_corpus_creates_transcript_files(tmp_path: Path) -> None:
    corpora = group_and_scrub(_raw_calls())
    eva = corpora["agent_ent_eva"]
    stats = write_corpus_to_disk(eva, tmp_path / "ent")
    assert stats["transcripts_written"] == 3
    files = list((tmp_path / "ent" / "transcripts").glob("*.txt"))
    assert {f.stem for f in files} == {"c1", "c2", "c4"}


def test_analyze_clinic_with_stub(tmp_path: Path) -> None:
    corpora = group_and_scrub(_raw_calls())
    eva = corpora["agent_ent_eva"]
    stub = _StubClient({
        "summary": "ENT scheduling with one chest-pain triage miss.",
        "happy_paths": [{"name": "basic_book", "description": "x",
                         "user_says_examples": ["Hi"], "frequency": "2/3"}],
        "failure_modes": [{"name": "chest_pain_misclassified",
                           "description": "agent scheduled instead of escalating",
                           "user_says_examples": ["I'm having chest pain"],
                           "agent_failure_pattern": "ignored emergency signal",
                           "occurred_in_calls": 1}],
        "derived_scenarios": [
            {"id": "chest_pain_must_escalate_ent",
             "description": "ENT-specific chest-pain triage check",
             "script": [{"user_says": "I'm having chest pain"}],
             "suite_asserts": ["assert_no_crash"]},
        ],
        "kb_coverage_gaps": ["No documented after-hours number."],
        "recommended_tool_shapes": [],
    })
    analysis = analyze_clinic(eva, stub)
    assert stub.calls == 1
    assert analysis.summary.startswith("ENT scheduling")
    assert len(analysis.derived_scenarios) == 1
    assert "after-hours" in analysis.kb_coverage_gaps[0]


def test_analysis_md_renders_sections() -> None:
    analysis = ClinicAnalysis(
        agent_id="x", agent_name="Test Clinic", specialty="ent",
        summary="One-line summary.",
        happy_paths=[{"name": "p1", "description": "d1",
                      "user_says_examples": ["hi"], "frequency": "1/2",
                      "expected_tool_calls": ["check_availability"]}],
        failure_modes=[{"name": "f1", "description": "d2",
                        "agent_failure_pattern": "ignored signal",
                        "occurred_in_calls": 2,
                        "user_says_examples": ["chest pain"]}],
        kb_coverage_gaps=["After-hours number missing"],
        recommended_tool_shapes=[{"tool_name": "book",
                                   "suggested_assertions": ["regex on phone"]}],
        derived_scenarios=[{"id": "test_clinic__x", "description": "y",
                            "script": [{"user_says": "z"}],
                            "suite_asserts": ["assert_no_crash"]}],
    )
    md = render_analysis_md(analysis)
    assert "Happy paths observed" in md
    assert "Failure modes observed" in md
    assert "KB coverage gaps" in md
    assert "Recommended tool-shape contracts" in md
    assert "check_availability" in md


def test_synthesizer_merges_library_with_derived(tmp_path: Path) -> None:
    meta = AgentMeta(
        provider="retell", agent_name="Test Clinic", language="en-US",
        languages_supported=["en"], voice_id=None,
        global_prompt="You are a scheduler.", node_names=[],
        tools=[], knowledge_base_ids=[],
        has_knowledge_base=False, references_kb_in_prompt=False,
        detected_specialty="ent",
    )
    analysis = ClinicAnalysis(
        agent_id="agent_x", agent_name="Test Clinic", specialty="ent",
        derived_scenarios=[
            {"id": "after_hours_specialty_ent",
             "description": "Caller asks about ENT after-hours",
             "script": [{"user_says": "I have a really bad earache at 10pm"}],
             "suite_asserts": ["assert_no_crash"]},
        ],
    )
    suite = merge_suite(meta, analysis)
    ids = [c["id"] for c in suite["cases"]]
    # Library scenario survived.
    assert "urgent_chest_pain_triage_must_escalate" in ids
    # Derived scenario added and prefixed with clinic slug.
    assert any(cid.endswith("after_hours_specialty_ent") for cid in ids)


def test_write_clinic_suite_round_trip(tmp_path: Path) -> None:
    """The full directory layout: voxeval.yaml + analysis.md + transcripts/."""
    meta = AgentMeta(
        provider="retell", agent_name="ENT-SD", language="en-US",
        languages_supported=["en"], voice_id=None,
        global_prompt="x", node_names=[], tools=[],
        knowledge_base_ids=[], has_knowledge_base=False,
        references_kb_in_prompt=False, detected_specialty="ent",
    )
    analysis = ClinicAnalysis(
        agent_id="agent_ent_eva", agent_name="ENT-SD", specialty="ent",
        summary="Quick narrative", derived_scenarios=[],
    )
    yaml_path = write_clinic_suite(tmp_path / "ent-sd", meta, analysis)
    assert yaml_path.exists()
    text = yaml_path.read_text()
    assert text.startswith("# Auto-generated")
    body = yaml.safe_load(text)
    assert body["provider"]["name"] == "retell"
    assert (tmp_path / "ent-sd" / "analysis.md").exists()
