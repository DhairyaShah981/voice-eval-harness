"""VapiConnector unit tests via httpx.MockTransport."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from voice_eval_harness.connectors.vapi import VapiConnector
from voice_eval_harness.core.models import ProviderSpec, Role, TestCase


def _handler(history: list[httpx.Request]) -> httpx.MockTransport:
    def respond(request: httpx.Request) -> httpx.Response:
        history.append(request)
        if request.url.path == "/chat":
            return httpx.Response(200, json={
                "id": "chat_vapi_1",
                "output": [
                    {"role": "assistant", "content": "Hi! How can I help?",
                     "toolCalls": []},
                ],
            })
        return httpx.Response(404, json={})
    return httpx.MockTransport(respond)


def test_vapi_create_chat_and_continue() -> None:
    async def run() -> None:
        history: list[httpx.Request] = []
        client = httpx.AsyncClient(
            transport=_handler(history),
            base_url="https://api.vapi.test",
            headers={"Authorization": "Bearer x"},
        )
        cfg = ProviderSpec(name="vapi", api_key="x", agent_id="asst_1")
        conn = VapiConnector(cfg, http_client=client)
        case = TestCase(id="v1")
        session = await conn.start_session(case)
        reply = await session.send_user_turn("Hello")
        assert reply.role == Role.AGENT
        assert "help" in (reply.text or "").lower()
        # Second turn should attach previousChatId.
        await session.send_user_turn("Thanks")
        bodies = [r.content.decode() for r in history]
        assert "previousChatId" in bodies[1]
        await session.end()

    asyncio.run(run())


def test_vapi_missing_assistant_raises() -> None:
    with pytest.raises(ValueError, match="agent_id"):
        VapiConnector(ProviderSpec(name="vapi", api_key="x"))
