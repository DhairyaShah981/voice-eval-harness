"""RetellConnector — text-mode via Retell's chat endpoints.

Wraps:
  POST {base_url}/create-chat              -> {chat_id, ...}
  POST {base_url}/create-chat-completion   -> {messages: [...]}

Audio-mode (POST /create-phone-call) lands in v0.2 with a --allow-audio
flag and a hard --max-cost guardrail. Text-mode is text/transcript only
and is the safe path for CI.

The connector accepts an optional ``http_client`` so tests can pass an
``httpx.AsyncClient`` with a ``MockTransport`` and avoid the network.
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

DEFAULT_BASE_URL = "https://api.retellai.com"


def _extract_agent_text_and_tools(
    messages: list[dict[str, Any]],
    base_ts: float,
) -> list[TranscriptEvent]:
    """Convert Retell's mixed message stream into TranscriptEvent objects.

    Retell's response includes Message / ToolCallInvocationMessage /
    ToolCallResultMessage / NodeTransitionMessage / StateTransitionMessage.
    """
    out: list[TranscriptEvent] = []
    for m in messages:
        if not isinstance(m, dict):
            continue
        role = (m.get("role") or "").lower()
        ts_ms = int(((m.get("created_timestamp") or time.time()) - base_ts) * 1000)
        if role == "agent":
            out.append(TranscriptEvent(
                ts_ms=max(ts_ms, 0), role=Role.AGENT,
                text=m.get("content") or "",
            ))
        elif role == "user":
            out.append(TranscriptEvent(
                ts_ms=max(ts_ms, 0), role=Role.USER,
                text=m.get("content") or "",
            ))
        elif role == "tool_call_invocation":
            out.append(TranscriptEvent(
                ts_ms=max(ts_ms, 0), role=Role.TOOL,
                tool_name=m.get("name"),
                tool_args=m.get("arguments") if isinstance(m.get("arguments"), dict)
                          else {"raw": m.get("arguments")},
            ))
        elif role == "tool_call_result":
            out.append(TranscriptEvent(
                ts_ms=max(ts_ms, 0), role=Role.TOOL,
                tool_name=m.get("name") or "<result>",
                tool_args={"content": m.get("content"),
                           "successful": m.get("successful")},
            ))
        else:
            # node_transition / state_transition / other — kept as system events.
            out.append(TranscriptEvent(
                ts_ms=max(ts_ms, 0), role=Role.SYSTEM,
                text=f"[{role}]",
                extra={k: v for k, v in m.items()
                       if k not in ("role", "message_id", "created_timestamp")},
            ))
    return out


class _RetellSession(Session):
    def __init__(
        self,
        client: httpx.AsyncClient,
        chat_id: str,
        agent_id: str,
    ) -> None:
        self._client = client
        self._chat_id = chat_id
        self._agent_id = agent_id
        self._events: list[TranscriptEvent] = []
        self._start = time.time()
        self._latencies: list[float] = []

    async def send_user_turn(
        self,
        text: str,
        *,
        lang: str | None = None,
        interrupt_at_ms: int | None = None,
    ) -> TranscriptEvent:
        user_ev = TranscriptEvent(
            ts_ms=int((time.time() - self._start) * 1000),
            role=Role.USER, text=text,
            extra={"lang": lang} if lang else {},
        )
        self._events.append(user_ev)

        t0 = time.monotonic()
        resp = await self._client.post(
            "/create-chat-completion",
            json={"chat_id": self._chat_id, "content": text},
        )
        resp.raise_for_status()
        payload = resp.json()
        elapsed_ms = (time.monotonic() - t0) * 1000.0
        self._latencies.append(elapsed_ms)

        messages = payload.get("messages") or []
        evts = _extract_agent_text_and_tools(messages, self._start)
        # Filter out any echo of the user message — we already recorded it.
        evts = [
            e for e in evts
            if not (e.role == Role.USER and (e.text or "").strip() == text.strip())
        ]
        self._events.extend(evts)

        # Return the most recent agent event for callers that want it.
        for e in reversed(evts):
            if e.role == Role.AGENT:
                return e
        # No agent text in this turn — synthesize a placeholder so the
        # engine never gets None.
        return TranscriptEvent(
            ts_ms=int((time.time() - self._start) * 1000),
            role=Role.AGENT, text="",
        )

    async def stream_events(self) -> AsyncIterator[TranscriptEvent]:
        async def _gen() -> AsyncIterator[TranscriptEvent]:
            if False:  # pragma: no cover — placeholder, M5 wires streaming
                yield  # type: ignore[unreachable]
        return _gen()

    async def end(self) -> CallSummary:
        latencies = sorted(self._latencies)
        p50 = latencies[len(latencies) // 2] if latencies else None
        p95 = (latencies[int(len(latencies) * 0.95)]
               if len(latencies) >= 2 else (latencies[-1] if latencies else None))
        tool_invocations = [
            {"name": e.tool_name, "args": e.tool_args}
            for e in self._events
            if e.role == Role.TOOL and e.tool_name and e.tool_name != "<result>"
        ]
        return CallSummary(
            disconnect_reason="completed",
            latency_p50_ms=p50,
            latency_p95_ms=p95,
            cost_usd=0.0,  # Retell doesn't bill text-chat per call in this API
            tool_invocations=tool_invocations,
        )

    @property
    def transcript(self) -> list[TranscriptEvent]:
        return list(self._events)


class RetellConnector(BaseConnector):
    name = "retell"
    supports_audio = False  # audio-mode lands in v0.2

    def __init__(
        self,
        cfg: ProviderSpec,
        *,
        http_client: httpx.AsyncClient | None = None,
        base_url: str | None = None,
    ) -> None:
        super().__init__(cfg)
        api_key = cfg.api_key or os.environ.get("RETELL_API_KEY", "")
        if not api_key and http_client is None:
            raise ValueError(
                "RetellConnector requires `api_key` in provider config or "
                "RETELL_API_KEY env var (use http_client= for tests)."
            )
        if not cfg.agent_id:
            raise ValueError("RetellConnector requires `agent_id` in provider config.")
        self._agent_id = cfg.agent_id
        if http_client is None:
            http_client = httpx.AsyncClient(
                base_url=base_url or DEFAULT_BASE_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                timeout=httpx.Timeout(30.0),
            )
        self._client = http_client

    async def start_session(self, case: TestCase) -> Session:
        resp = await self._client.post(
            "/create-chat",
            json={"agent_id": self._agent_id},
        )
        resp.raise_for_status()
        payload = resp.json()
        chat_id = payload.get("chat_id")
        if not chat_id:
            raise RuntimeError(
                f"Retell /create-chat returned no chat_id: {payload!r}"
            )
        return _RetellSession(
            client=self._client,
            chat_id=chat_id,
            agent_id=self._agent_id,
        )
