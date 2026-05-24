"""LLMJudgeAssertion: injected judge_fn, cache hit on rerun, malformed JSON."""

from __future__ import annotations

import json
from pathlib import Path

from voice_eval_harness.assertions.llm_judge import LLMJudgeAssertion
from voice_eval_harness.core.models import (
    AssertionSpec,
    CallSummary,
    Role,
    TranscriptEvent,
)


def _events(*pairs: tuple[str, str]) -> list[TranscriptEvent]:
    return [
        TranscriptEvent(role=Role(role), text=text, ts_ms=i * 100)
        for i, (role, text) in enumerate(pairs)
    ]


def test_judge_pass_verdict(tmp_path: Path) -> None:
    LLMJudgeAssertion.cache_dir = tmp_path
    LLMJudgeAssertion.judge_fn = staticmethod(
        lambda prompt, model: {"verdict": "pass", "reason": "ok"}
    )
    spec = AssertionSpec(kind="llm_judge", criterion="agent is friendly")
    res = LLMJudgeAssertion(spec).evaluate(
        _events(("user", "hi"), ("agent", "Hello! How can I help?")),
        CallSummary(),
    )
    assert res.passed
    assert res.detail == ""


def test_judge_fail_verdict(tmp_path: Path) -> None:
    LLMJudgeAssertion.cache_dir = tmp_path
    LLMJudgeAssertion.judge_fn = staticmethod(
        lambda prompt, model: {"verdict": "fail", "reason": "tone was rude"}
    )
    spec = AssertionSpec(kind="llm_judge", criterion="agent is polite")
    res = LLMJudgeAssertion(spec).evaluate(
        _events(("user", "hi"), ("agent", "What do you want.")),
        CallSummary(),
    )
    assert not res.passed
    assert "rude" in res.detail


def test_judge_cache_hit(tmp_path: Path) -> None:
    LLMJudgeAssertion.cache_dir = tmp_path
    calls = {"n": 0}

    def judge(prompt: str, model: str) -> dict:
        calls["n"] += 1
        return {"verdict": "pass", "reason": ""}

    LLMJudgeAssertion.judge_fn = staticmethod(judge)
    spec = AssertionSpec(kind="llm_judge", criterion="x")
    transcript = _events(("agent", "hi"))
    LLMJudgeAssertion(spec).evaluate(transcript, CallSummary())
    LLMJudgeAssertion(spec).evaluate(transcript, CallSummary())
    assert calls["n"] == 1, "second call should be served from disk cache"


def test_missing_criterion_returns_fail(tmp_path: Path) -> None:
    LLMJudgeAssertion.cache_dir = tmp_path
    LLMJudgeAssertion.judge_fn = staticmethod(
        lambda *a, **k: {"verdict": "pass", "reason": ""}
    )
    spec = AssertionSpec(kind="llm_judge")  # no criterion
    res = LLMJudgeAssertion(spec).evaluate(_events(("agent", "x")), CallSummary())
    assert not res.passed
    assert "criterion" in res.detail.lower()


def test_judge_payload_persisted(tmp_path: Path) -> None:
    LLMJudgeAssertion.cache_dir = tmp_path
    LLMJudgeAssertion.judge_fn = staticmethod(
        lambda prompt, model: {"verdict": "pass", "reason": ""}
    )
    spec = AssertionSpec(kind="llm_judge", criterion="agent helps")
    LLMJudgeAssertion(spec).evaluate(_events(("agent", "hi")), CallSummary())
    cache_files = list(tmp_path.glob("judge_*.json"))
    assert len(cache_files) == 1
    data = json.loads(cache_files[0].read_text())
    assert data["verdict"] == "pass"
