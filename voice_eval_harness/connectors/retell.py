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
    supports_audio = True  # audio-mode behind the --allow-audio gate

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
        # Optional audio-mode wiring (read from extra fields on the provider
        # spec). All audio fields are validated lazily on first audio call.
        extra = cfg.model_dump()
        self._from_number: str | None = extra.get("from_number")
        self._to_number: str | None = extra.get("to_number")
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
        if case.mode == "audio":
            return await self._start_audio_session(case)
        resp = await self._client.post(
            "/create-chat",
            json={"agent_id": self._agent_id},
        )
        if resp.status_code == 422:
            # The most common cause: agent is registered with channel=voice
            # and Retell rejects text-chat sessions against it. Voxeval text
            # mode needs a chat-channel agent (or a duplicate of the voice
            # agent registered with channel=chat in the Retell dashboard).
            raise RuntimeError(
                f"Retell rejected text-chat session for agent {self._agent_id!r} "
                f"(HTTP 422). Most common cause: the agent is registered as "
                f"channel=voice and does not accept text chat. "
                f"Fix options: (1) register a parallel chat-channel agent in "
                f"the Retell dashboard with the same prompt/tools, or "
                f"(2) wait for voxeval v0.2 audio-mode. Server said: "
                f"{resp.text[:300]}"
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

    async def _start_audio_session(self, case: TestCase) -> Session:
        """Outbound phone-call session via Retell `/create-phone-call`.

        Costs real money per minute. Gated behind ``--allow-audio`` in
        ``voxeval run``; raises if the harness wasn't asked to use audio.
        """
        import os as _os
        if _os.environ.get("VOXEVAL_ALLOW_AUDIO") != "1":
            raise RuntimeError(
                "Retell audio-mode requires the --allow-audio flag on "
                "`voxeval run` (sets VOXEVAL_ALLOW_AUDIO=1) to acknowledge "
                "that this WILL bill your Retell account per minute. "
                "Combine with --max-cost to bound the spend."
            )
        if not (self._from_number and self._to_number):
            raise RuntimeError(
                "Retell audio-mode requires `from_number` and `to_number` "
                "in provider config (Retell-purchased PSTN numbers)."
            )
        resp = await self._client.post("/create-phone-call", json={
            "from_number": self._from_number,
            "to_number": self._to_number,
            "override_agent_id": self._agent_id,
        })
        resp.raise_for_status()
        payload = resp.json()
        call_id = payload.get("call_id")
        if not call_id:
            raise RuntimeError(
                f"Retell /create-phone-call returned no call_id: {payload!r}"
            )
        return _RetellAudioSession(client=self._client, call_id=call_id)


class _RetellAudioSession(Session):
    """Wraps a live PSTN call; polls /get-call/{id} for the final transcript."""

    POLL_INTERVAL_S = 5.0
    MAX_WAIT_S = 600.0   # 10 minutes hard cap

    def __init__(self, client: httpx.AsyncClient, call_id: str) -> None:
        self._client = client
        self._call_id = call_id
        self._events: list[TranscriptEvent] = []
        self._call: dict[str, Any] = {}

    async def send_user_turn(
        self, text: str, *, lang: str | None = None,
        interrupt_at_ms: int | None = None,
    ) -> TranscriptEvent:
        # Audio-mode: the live caller drives the call, not the engine. The
        # script in YAML is informational only.
        raise NotImplementedError(
            "Audio-mode sessions are passive — the live PSTN caller drives "
            "the call. Drop the `script:` entries from your YAML or move to "
            "text-mode for scripted multi-turn tests."
        )

    async def stream_events(self) -> AsyncIterator[TranscriptEvent]:
        async def _gen() -> AsyncIterator[TranscriptEvent]:
            if False:  # pragma: no cover
                yield  # type: ignore[unreachable]
        return _gen()

    async def end(self) -> CallSummary:
        import asyncio as _asyncio
        import time as _time
        deadline = _time.monotonic() + self.MAX_WAIT_S
        call: dict[str, Any] = {}
        while _time.monotonic() < deadline:
            resp = await self._client.get(f"/get-call/{self._call_id}")
            resp.raise_for_status()
            call = resp.json()
            if call.get("call_status") == "ended":
                break
            await _asyncio.sleep(self.POLL_INTERVAL_S)
        self._call = call

        transcript_text = call.get("transcript") or ""
        # Parse the plain-text transcript into events (User:/Agent: lines).
        for i, line in enumerate(transcript_text.splitlines()):
            line = line.strip()
            if not line:
                continue
            if line.lower().startswith("user:"):
                self._events.append(TranscriptEvent(
                    ts_ms=i, role=Role.USER, text=line.split(":", 1)[1].strip(),
                ))
            elif line.lower().startswith("agent:"):
                self._events.append(TranscriptEvent(
                    ts_ms=i, role=Role.AGENT, text=line.split(":", 1)[1].strip(),
                ))

        latency = call.get("latency") or {}
        cost_block = call.get("call_cost") or {}
        return CallSummary(
            disconnect_reason=call.get("disconnection_reason"),
            latency_p50_ms=latency.get("e2e_p50"),
            latency_p95_ms=latency.get("e2e_p95"),
            cost_usd=float(cost_block.get("combined_cost", 0)) / 100.0,
            tool_invocations=call.get("tool_calls") or [],
        )

    @property
    def transcript(self) -> list[TranscriptEvent]:
        return list(self._events)
