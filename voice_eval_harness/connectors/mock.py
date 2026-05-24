"""MockConnector — deterministic in-memory connector for self-tests and CI.

Behaviour:
  - Responses are configured per case id via the provider config:
    ``responses: { case_id_1: ["agent reply 1", "agent reply 2"], ... }``.
  - If no entry exists for a case, every user turn echoes back as
    ``"mock-ack: <user text>"`` so simple suites still produce a transcript.
  - Tool calls can be staged via
    ``tool_calls: { case_id: [{turn: 0, name: "x", args: {...}}, ...] }``.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator

from voice_eval_harness.connectors.base import BaseConnector, Session
from voice_eval_harness.core.models import (
    CallSummary,
    ProviderSpec,
    Role,
    TestCase,
    TranscriptEvent,
)


class _MockSession(Session):
    def __init__(
        self,
        case_id: str,
        scripted_responses: list[str],
        scripted_tool_calls: list[dict],
    ) -> None:
        self._case_id = case_id
        self._responses = list(scripted_responses)
        self._tool_calls = list(scripted_tool_calls)
        self._events: list[TranscriptEvent] = []
        self._turn_idx = 0
        self._start = time.monotonic()
        self._pending_out_of_band: list[TranscriptEvent] = []

    def _now_ms(self) -> int:
        return int((time.monotonic() - self._start) * 1000)

    async def send_user_turn(
        self,
        text: str,
        *,
        lang: str | None = None,
        interrupt_at_ms: int | None = None,
    ) -> TranscriptEvent:
        user_ev = TranscriptEvent(
            ts_ms=self._now_ms(), role=Role.USER, text=text,
            extra={"lang": lang} if lang else {},
        )
        self._events.append(user_ev)

        # Stage any tool calls scheduled for this turn.
        for tc in self._tool_calls:
            if tc.get("turn") == self._turn_idx:
                tool_ev = TranscriptEvent(
                    ts_ms=self._now_ms(), role=Role.TOOL,
                    tool_name=tc.get("name"), tool_args=tc.get("args", {}),
                )
                self._events.append(tool_ev)
                self._pending_out_of_band.append(tool_ev)

        if self._turn_idx < len(self._responses):
            reply_text = self._responses[self._turn_idx]
        else:
            reply_text = f"mock-ack: {text}"
        self._turn_idx += 1
        reply = TranscriptEvent(
            ts_ms=self._now_ms(), role=Role.AGENT, text=reply_text,
        )
        self._events.append(reply)
        return reply

    async def stream_events(self) -> AsyncIterator[TranscriptEvent]:
        pending = list(self._pending_out_of_band)
        self._pending_out_of_band.clear()

        async def _gen() -> AsyncIterator[TranscriptEvent]:
            for ev in pending:
                yield ev
        return _gen()

    async def end(self) -> CallSummary:
        tool_invocations = [
            {"name": e.tool_name, "args": e.tool_args}
            for e in self._events
            if e.role == Role.TOOL
        ]
        return CallSummary(
            disconnect_reason="completed",
            latency_p50_ms=10.0,
            latency_p95_ms=20.0,
            cost_usd=0.0,
            tool_invocations=tool_invocations,
        )

    @property
    def transcript(self) -> list[TranscriptEvent]:
        return list(self._events)


class MockConnector(BaseConnector):
    name = "mock"
    supports_audio = False

    def __init__(self, cfg: ProviderSpec) -> None:
        super().__init__(cfg)
        extra = cfg.model_dump()
        self._responses: dict[str, list[str]] = extra.get("responses", {}) or {}
        self._tool_calls: dict[str, list[dict]] = extra.get("tool_calls", {}) or {}

    async def start_session(self, case: TestCase) -> Session:
        return _MockSession(
            case_id=case.id,
            scripted_responses=self._responses.get(case.id, []),
            scripted_tool_calls=self._tool_calls.get(case.id, []),
        )
