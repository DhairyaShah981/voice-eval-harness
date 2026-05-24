"""VapiConnector — text-mode via Vapi's /chat endpoint.

Wraps ``POST https://api.vapi.ai/chat`` with ``{input, assistantId,
previousChatId?}``. The first turn omits previousChatId; subsequent turns
chain via the returned chat id.

Audio-mode (``POST /call``) lands in v0.2 with --allow-audio + --max-cost.
"""

from __future__ import annotations

import os
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx

from voice_eval_harness.connectors.base import BaseConnector, Session
from voice_eval_harness.core.models import (
    CallSummary,
    ProviderSpec,
    Role,
    TestCase,
    TranscriptEvent,
)

DEFAULT_BASE_URL = "https://api.vapi.ai"


def _extract_assistant_text(payload: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    """Pull the assistant's output text + any tool invocations from a
    Vapi /chat response. Vapi's output is an array of messages; we
    concatenate any ``role=assistant`` content and collect tool calls.
    """
    output = payload.get("output") or payload.get("messages") or []
    text_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    if isinstance(output, list):
        for m in output:
            if not isinstance(m, dict):
                continue
            role = (m.get("role") or "").lower()
            if role == "assistant" and m.get("content"):
                text_parts.append(str(m["content"]))
            tcs = m.get("toolCalls") or m.get("tool_calls") or []
            if isinstance(tcs, list):
                for tc in tcs:
                    if isinstance(tc, dict):
                        fn = tc.get("function") or {}
                        tool_calls.append({
                            "name": fn.get("name") or tc.get("name"),
                            "args": fn.get("arguments") or tc.get("arguments") or {},
                        })
    return "\n".join(text_parts), tool_calls


class _VapiSession(Session):
    def __init__(
        self,
        client: httpx.AsyncClient,
        assistant_id: str,
    ) -> None:
        self._client = client
        self._assistant_id = assistant_id
        self._chat_id: str | None = None
        self._events: list[TranscriptEvent] = []
        self._tool_calls_all: list[dict[str, Any]] = []
        self._start = time.time()
        self._latencies: list[float] = []

    async def send_user_turn(
        self,
        text: str,
        *,
        lang: str | None = None,
        interrupt_at_ms: int | None = None,
    ) -> TranscriptEvent:
        self._events.append(TranscriptEvent(
            ts_ms=int((time.time() - self._start) * 1000),
            role=Role.USER, text=text,
        ))
        body: dict[str, Any] = {"assistantId": self._assistant_id, "input": text}
        if self._chat_id:
            body["previousChatId"] = self._chat_id

        t0 = time.monotonic()
        resp = await self._client.post("/chat", json=body)
        resp.raise_for_status()
        payload = resp.json()
        self._latencies.append((time.monotonic() - t0) * 1000.0)

        if payload.get("id"):
            self._chat_id = payload["id"]
        agent_text, tool_calls = _extract_assistant_text(payload)
        for tc in tool_calls:
            self._tool_calls_all.append(tc)
            self._events.append(TranscriptEvent(
                ts_ms=int((time.time() - self._start) * 1000),
                role=Role.TOOL,
                tool_name=tc.get("name"),
                tool_args=tc.get("args") if isinstance(tc.get("args"), dict)
                          else {"raw": tc.get("args")},
            ))
        agent_ev = TranscriptEvent(
            ts_ms=int((time.time() - self._start) * 1000),
            role=Role.AGENT, text=agent_text,
        )
        self._events.append(agent_ev)
        return agent_ev

    async def stream_events(self) -> AsyncIterator[TranscriptEvent]:
        async def _gen() -> AsyncIterator[TranscriptEvent]:
            if False:  # pragma: no cover
                yield  # type: ignore[unreachable]
        return _gen()

    async def end(self) -> CallSummary:
        latencies = sorted(self._latencies)
        p50 = latencies[len(latencies) // 2] if latencies else None
        p95 = (latencies[int(len(latencies) * 0.95)]
               if len(latencies) >= 2 else (latencies[-1] if latencies else None))
        return CallSummary(
            disconnect_reason="completed",
            latency_p50_ms=p50,
            latency_p95_ms=p95,
            cost_usd=0.0,
            tool_invocations=list(self._tool_calls_all),
        )

    @property
    def transcript(self) -> list[TranscriptEvent]:
        return list(self._events)


class VapiConnector(BaseConnector):
    name = "vapi"
    supports_audio = False

    def __init__(
        self,
        cfg: ProviderSpec,
        *,
        http_client: httpx.AsyncClient | None = None,
        base_url: str | None = None,
    ) -> None:
        super().__init__(cfg)
        api_key = cfg.api_key or os.environ.get("VAPI_API_KEY", "")
        if not api_key and http_client is None:
            raise ValueError(
                "VapiConnector requires `api_key` in provider config or "
                "VAPI_API_KEY env var (use http_client= for tests)."
            )
        if not cfg.agent_id:
            raise ValueError(
                "VapiConnector requires `agent_id` (Vapi assistant ID) in provider config."
            )
        self._assistant_id = cfg.agent_id
        if http_client is None:
            http_client = httpx.AsyncClient(
                base_url=base_url or DEFAULT_BASE_URL,
                headers={"Authorization": f"Bearer {api_key}",
                         "Content-Type": "application/json"},
                timeout=httpx.Timeout(30.0),
            )
        self._client = http_client

    async def start_session(self, case: TestCase) -> Session:
        return _VapiSession(client=self._client, assistant_id=self._assistant_id)
