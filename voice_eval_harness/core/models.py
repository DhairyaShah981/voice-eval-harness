"""Pydantic v2 data model for the entire eval harness.

These are the only types the rest of the codebase should pass around.
Everything else (connectors, assertions, engine) is built against these.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# ── Transcript / runtime types ───────────────────────────────────────────────


class Role(StrEnum):
    USER = "user"
    AGENT = "agent"
    TOOL = "tool"
    SYSTEM = "system"


class TranscriptEvent(BaseModel):
    """One thing that happened during a call: an utterance, a tool call,
    a system event. Ordered by ``ts_ms`` (monotonic milliseconds from start
    of the session)."""

    model_config = ConfigDict(extra="forbid")

    ts_ms: int = 0
    role: Role
    text: str | None = None
    tool_name: str | None = None
    tool_args: dict[str, Any] | None = None
    audio_uri: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class CallSummary(BaseModel):
    """End-of-session aggregates a connector hands back."""

    model_config = ConfigDict(extra="forbid")

    disconnect_reason: str | None = None
    latency_p50_ms: float | None = None
    latency_p95_ms: float | None = None
    cost_usd: float = 0.0
    tool_invocations: list[dict[str, Any]] = Field(default_factory=list)


# ── Assertion model ──────────────────────────────────────────────────────────


class AssertionSpec(BaseModel):
    """Normalized assertion spec. The YAML grammar allows several shorthands
    (bare string, ``{assert_KIND: value}`` dict, etc.); ``config.py``
    normalizes them all into this single shape so the engine + assertion
    registry only deal with one form."""

    model_config = ConfigDict(extra="allow")

    kind: str
    # Free-form payload — each Assertion subclass reads the keys it needs.


class AssertionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    passed: bool
    detail: str = ""


# ── Test case model ──────────────────────────────────────────────────────────


class PersonaSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["impatient", "accented", "code_switching", "kb_probing"]
    params: dict[str, Any] = Field(default_factory=dict)


class Turn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_says: str | None = None
    interrupt_at_ms: int | None = None
    language: str | None = None
    asserts: list[AssertionSpec] = Field(default_factory=list)


class TestCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    description: str = ""
    persona: PersonaSpec | None = None
    script: list[Turn] = Field(default_factory=list)
    suite_asserts: list[AssertionSpec] = Field(default_factory=list)
    mode: Literal["text", "audio"] = "text"
    timeout_s: int = 60
    retries: int = 0


# ── Suite / provider model ───────────────────────────────────────────────────


class ProviderSpec(BaseModel):
    """Free-form provider config — each connector validates its own subset."""

    model_config = ConfigDict(extra="allow")

    name: str
    api_key: str | None = None
    agent_id: str | None = None
    agent_json: str | None = None  # path for pre-flight lint


class DefaultsSpec(BaseModel):
    model_config = ConfigDict(extra="allow")

    mode: Literal["text", "audio"] = "text"
    timeout_s: int = 45
    judge_model: str = "gpt-4o-mini-2024-07-18"


class KBCoverageSpec(BaseModel):
    """Reserved for M6 — present so YAML parses today."""

    model_config = ConfigDict(extra="allow")

    source: str
    generator: str = "gpt-4o"
    sample_size: int = 50
    min_pass_rate: float = 0.85


class ReplaySpec(BaseModel):
    """Reserved for M7 — present so YAML parses today."""

    model_config = ConfigDict(extra="allow")

    from_: str = Field(alias="from")
    since: str = "7d"
    status: list[str] = Field(default_factory=list)
    max_cases: int = 25


class EvalSuite(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    provider: ProviderSpec
    defaults: DefaultsSpec = Field(default_factory=DefaultsSpec)
    cases: list[TestCase] = Field(default_factory=list)
    kb_coverage: KBCoverageSpec | None = None
    replay: ReplaySpec | None = None


# ── Run-result types ─────────────────────────────────────────────────────────


class RunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    passed: bool
    duration_ms: int
    transcript: list[TranscriptEvent] = Field(default_factory=list)
    assertion_results: list[AssertionResult] = Field(default_factory=list)
    cost_usd: float = 0.0
    error: str | None = None


class SuiteResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cases: list[RunResult] = Field(default_factory=list)
    total_cost_usd: float = 0.0
    # Optional per-persona breakdown — populated by the engine when at least
    # one case has a persona. Maps persona type ("impatient", ...) -> aggregate.
    cost_by_persona: dict[str, dict[str, float | int]] = Field(default_factory=dict)

    @property
    def passed(self) -> int:
        return sum(1 for c in self.cases if c.passed)

    @property
    def failed(self) -> int:
        return sum(1 for c in self.cases if not c.passed)

    @property
    def ok(self) -> bool:
        return self.failed == 0 and len(self.cases) > 0
