"""voxeval audit pipeline + Retell audio-mode session unit tests."""

from __future__ import annotations

import asyncio
import os

import httpx
import pytest

from voice_eval_harness.connectors.retell import RetellConnector
from voice_eval_harness.core.models import ProviderSpec, TestCase

# ── Audio-mode connector tests ───────────────────────────────────────────────


def _audio_handler(history: list[httpx.Request]) -> httpx.MockTransport:
    def respond(request: httpx.Request) -> httpx.Response:
        history.append(request)
        if request.url.path == "/create-phone-call":
            return httpx.Response(201, json={
                "call_id": "call_audio_test_001",
                "agent_id": "agent_x",
            })
        if request.url.path.startswith("/get-call/"):
            return httpx.Response(200, json={
                "call_id": "call_audio_test_001",
                "call_status": "ended",
                "transcript": "User: I need an appointment\nAgent: Sure, when?",
                "disconnection_reason": "user_hangup",
                "latency": {"e2e_p50": 1100, "e2e_p95": 1700},
                "call_cost": {"combined_cost": 24.5},
            })
        return httpx.Response(404, json={})
    return httpx.MockTransport(respond)


def _audio_connector(history: list[httpx.Request]) -> RetellConnector:
    client = httpx.AsyncClient(
        transport=_audio_handler(history),
        base_url="https://api.retellai.test",
        headers={"Authorization": "Bearer x"},
    )
    cfg = ProviderSpec.model_validate({
        "name": "retell", "api_key": "x", "agent_id": "agent_x",
        "from_number": "+15550000001",
        "to_number": "+15550000002",
    })
    return RetellConnector(cfg, http_client=client)


def test_audio_mode_requires_allow_audio_flag(monkeypatch) -> None:
    """Audio-mode start_session must refuse unless VOXEVAL_ALLOW_AUDIO=1."""
    monkeypatch.delenv("VOXEVAL_ALLOW_AUDIO", raising=False)
    async def go() -> None:
        history: list[httpx.Request] = []
        conn = _audio_connector(history)
        case = TestCase(id="a1", mode="audio")
        with pytest.raises(RuntimeError, match="--allow-audio"):
            await conn.start_session(case)
    asyncio.run(go())


def test_audio_mode_polls_until_ended(monkeypatch) -> None:
    monkeypatch.setenv("VOXEVAL_ALLOW_AUDIO", "1")
    async def go() -> None:
        history: list[httpx.Request] = []
        conn = _audio_connector(history)
        # Make the poll instant for the test.
        from voice_eval_harness.connectors import retell as r
        r._RetellAudioSession.POLL_INTERVAL_S = 0.0
        session = await conn.start_session(TestCase(id="a1", mode="audio"))
        summary = await session.end()
        assert summary.disconnect_reason == "user_hangup"
        assert summary.latency_p50_ms == 1100
        assert summary.cost_usd > 0
        events = session.transcript
        assert any("appointment" in (e.text or "") for e in events)
        # Verify both endpoints hit.
        paths = [r.url.path for r in history]
        assert "/create-phone-call" in paths
        assert any(p.startswith("/get-call/") for p in paths)
    asyncio.run(go())


def test_audio_mode_send_user_turn_raises() -> None:
    """Audio sessions are passive — engine must not try to script turns."""
    os.environ["VOXEVAL_ALLOW_AUDIO"] = "1"
    async def go() -> None:
        history: list[httpx.Request] = []
        conn = _audio_connector(history)
        from voice_eval_harness.connectors import retell as r
        r._RetellAudioSession.POLL_INTERVAL_S = 0.0
        session = await conn.start_session(TestCase(id="a1", mode="audio"))
        with pytest.raises(NotImplementedError, match="passive"):
            await session.send_user_turn("hi")
    try:
        asyncio.run(go())
    finally:
        os.environ.pop("VOXEVAL_ALLOW_AUDIO", None)


# ── Stub connector tests ─────────────────────────────────────────────────────


def test_stub_connectors_register_and_raise_with_clear_message() -> None:
    from voice_eval_harness.core.registry import CONNECTORS, get_connector
    for name in ("livekit", "pipecat", "bland"):
        assert name in CONNECTORS, f"{name} stub must be registered"
        conn = get_connector(ProviderSpec(name=name))

        async def _check(c=conn) -> None:
            with pytest.raises(NotImplementedError):
                await c.start_session(TestCase(id="x"))

        asyncio.run(_check())
