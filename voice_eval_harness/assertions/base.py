"""Assertion ABC and built-in assertions for v0.1.

Assertions are pure functions of the transcript + the call summary. They
do not perform I/O (the LLM-judge assertion lives in ``llm_judge.py`` and
is the only one that does).

Each Assertion subclass declares the ``kind`` string the YAML/normalizer
emits for it. The registry below ties kind → class.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar

from voice_eval_harness.core.models import (
    AssertionResult,
    AssertionSpec,
    CallSummary,
    Role,
    TranscriptEvent,
)


class Assertion(ABC):
    kind: ClassVar[str] = ""

    def __init__(self, spec: AssertionSpec) -> None:
        self.spec = spec
        self.params = spec.model_dump(exclude={"kind"})

    @abstractmethod
    def evaluate(
        self, transcript: list[TranscriptEvent], summary: CallSummary,
    ) -> AssertionResult: ...


def _agent_text(transcript: list[TranscriptEvent]) -> str:
    return "\n".join(e.text or "" for e in transcript if e.role == Role.AGENT)


class ContainsAssertion(Assertion):
    kind = "contains"

    def evaluate(self, transcript, summary):  # type: ignore[override]
        values = self.params.get("values") or []
        text = _agent_text(transcript)
        missing = [v for v in values if v.lower() not in text.lower()]
        ok = not missing
        detail = "" if ok else f"missing in agent text: {missing}"
        return AssertionResult(kind=self.kind, passed=ok, detail=detail)


class NotContainsAssertion(Assertion):
    kind = "not_contains"

    def evaluate(self, transcript, summary):  # type: ignore[override]
        values = self.params.get("values") or []
        text = _agent_text(transcript)
        hits = [v for v in values if v.lower() in text.lower()]
        ok = not hits
        detail = "" if ok else f"forbidden strings appeared: {hits}"
        return AssertionResult(kind=self.kind, passed=ok, detail=detail)


class NoCrashAssertion(Assertion):
    kind = "no_crash"

    def evaluate(self, transcript, summary):  # type: ignore[override]
        bad = (summary.disconnect_reason or "").lower()
        crashed = any(
            tok in bad for tok in ("error", "crash", "exception", "agent_error")
        )
        return AssertionResult(
            kind=self.kind, passed=not crashed,
            detail="" if not crashed else f"disconnect_reason={summary.disconnect_reason!r}",
        )


class LatencyMsAssertion(Assertion):
    kind = "latency_ms"

    def evaluate(self, transcript, summary):  # type: ignore[override]
        p95_lt = self.params.get("p95_lt")
        p50_lt = self.params.get("p50_lt")
        problems: list[str] = []
        if p50_lt is not None and (summary.latency_p50_ms or 0) >= p50_lt:
            problems.append(f"p50={summary.latency_p50_ms} >= {p50_lt}")
        if p95_lt is not None and (summary.latency_p95_ms or 0) >= p95_lt:
            problems.append(f"p95={summary.latency_p95_ms} >= {p95_lt}")
        ok = not problems
        return AssertionResult(
            kind=self.kind, passed=ok, detail="" if ok else "; ".join(problems),
        )


class ToolCalledAssertion(Assertion):
    kind = "tool_called"

    def evaluate(self, transcript, summary):  # type: ignore[override]
        want = self.params.get("tool_name")
        names = [t.get("name") for t in summary.tool_invocations]
        ok = want in names
        return AssertionResult(
            kind=self.kind, passed=ok,
            detail="" if ok else f"expected tool {want!r}, saw: {names}",
        )


class ToolArgsAssertion(Assertion):
    kind = "tool_args"

    def evaluate(self, transcript, summary):  # type: ignore[override]
        want: dict[str, Any] = self.params.get("args") or {}
        for inv in summary.tool_invocations:
            args = inv.get("args") or {}
            if all(args.get(k) == v for k, v in want.items()):
                return AssertionResult(kind=self.kind, passed=True)
        return AssertionResult(
            kind=self.kind, passed=False,
            detail=f"no tool invocation matched expected args {want}",
        )


class LanguageAssertion(Assertion):
    kind = "language"

    def evaluate(self, transcript, summary):  # type: ignore[override]
        want = (self.params.get("code") or "").lower()
        # Heuristic v0.1: scan any agent turn for per-language markers. M5
        # swaps in real langdetect with confidence thresholds.
        markers = {
            "es": ("hola", "gracias", "por favor", "necesito", "buenos",
                   "supuesto", "disponibilidad", "señor", "señora", "ñ"),
            "en": ("hello", "thanks", "please", "appointment", "thank"),
            "hi": ("namaste", "धन्यवाद", "कृपया", "मुझे"),
            "fr": ("bonjour", "merci", "s'il vous", "rendez-vous"),
        }
        agent_text = " ".join(
            (e.text or "").lower() for e in transcript if e.role == Role.AGENT
        )
        if not agent_text.strip():
            return AssertionResult(kind=self.kind, passed=False,
                                   detail="no agent turn to language-check")
        bank = markers.get(want, ())
        ok = any(m in agent_text for m in bank)
        return AssertionResult(
            kind=self.kind, passed=ok,
            detail="" if ok else f"no {want!r} markers found across agent turns",
        )


class PiiRedactedAssertion(Assertion):
    """v0.1 sentinel: ensures no obvious patterns (SSN, MRN, credit-card)
    leak in the agent transcript. M7 will swap in Presidio."""

    kind = "pii_redacted"

    def evaluate(self, transcript, summary):  # type: ignore[override]
        import re
        joined = " ".join(e.text or "" for e in transcript if e.role == Role.AGENT)
        patterns = {
            "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
            "credit_card": r"\b(?:\d[ -]?){13,16}\b",
        }
        leaks = [k for k, p in patterns.items() if re.search(p, joined)]
        ok = not leaks
        return AssertionResult(
            kind=self.kind, passed=ok,
            detail="" if ok else f"PII patterns detected: {leaks}",
        )


BUILTIN_ASSERTIONS: dict[str, type[Assertion]] = {
    cls.kind: cls
    for cls in (
        ContainsAssertion,
        NotContainsAssertion,
        NoCrashAssertion,
        LatencyMsAssertion,
        ToolCalledAssertion,
        ToolArgsAssertion,
        LanguageAssertion,
        PiiRedactedAssertion,
    )
}

# Register tool_shape via its own module (keeps the file modular).
from voice_eval_harness.assertions.tool_shape import register as _register_tool_shape  # noqa: E402

_register_tool_shape(BUILTIN_ASSERTIONS)


def build_assertion(spec: AssertionSpec) -> Assertion:
    # Lazy import to avoid a hard dependency on llm_judge module at import
    # of this file (which is hot-loaded by the engine on every run).
    if spec.kind == "llm_judge":
        from voice_eval_harness.assertions.llm_judge import LLMJudgeAssertion
        return LLMJudgeAssertion(spec)
    cls = BUILTIN_ASSERTIONS.get(spec.kind)
    if cls is None:
        raise ValueError(
            f"unknown assertion kind {spec.kind!r}; "
            f"known: {sorted([*BUILTIN_ASSERTIONS, 'llm_judge'])}"
        )
    return cls(spec)
