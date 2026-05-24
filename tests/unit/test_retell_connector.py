"""Unit tests for RetellConnector using httpx.MockTransport.

These tests do not touch the network — they verify the connector speaks the
right Retell chat protocol against a deterministic stub. The live smoke test
runs separately and requires a real RETELL_API_KEY.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from voice_eval_harness.connectors.retell import RetellConnector
from voice_eval_harness.core.models import ProviderSpec, Role, TestCase


def _handler(history: list[httpx.Request]) -> httpx.MockTransport:
    """Build a MockTransport that records requests and returns canned responses."""

    def respond(request: httpx.Request) -> httpx.Response:
        history.append(request)
        if request.url.path == "/create-chat":
            return httpx.Response(201, json={
                "chat_id": "chat_test_abc",
                "agent_id": "agent_test",
                "chat_status": "ongoing",
                "chat_type": "api_chat",
                "transcript": "",
                "message_with_tool_calls": [],
                "metadata": {},
                "chat_cost": {},
                "chat_analysis": {},
                "start_timestamp": 0,
                "end_timestamp": None,
                "retell_llm_dynamic_variables": {},
                "collected_dynamic_variables": {},
                "custom_attributes": {},
                "version": None,
            })
        if request.url.path == "/create-chat-completion":
            body = request.content.decode()
            if "Hola" in body:
                return httpx.Response(201, json={
                    "messages": [
                        {"role": "agent",
                         "content": "Hola, gracias por llamar. ¿En qué puedo ayudarle?",
                         "message_id": "m1", "created_timestamp": 0},
                    ],
                })
            if "tuesday" in body.lower() or "martes" in body.lower():
                return httpx.Response(201, json={
                    "messages": [
                        {"role": "tool_call_invocation",
                         "tool_call_id": "tc1",
                         "name": "get_available_slots",
                         "arguments": {"day_of_week": "tuesday"},
                         "message_id": "m2", "created_timestamp": 0},
                        {"role": "tool_call_result",
                         "tool_call_id": "tc1",
                         "content": "[\"10am\",\"11am\"]",
                         "successful": True,
                         "message_id": "m3", "created_timestamp": 0},
                        {"role": "agent",
                         "content": "Tengo disponibilidad a las 10 y a las 11.",
                         "message_id": "m4", "created_timestamp": 0},
                    ],
                })
            return httpx.Response(201, json={
                "messages": [
                    {"role": "agent", "content": "Hi! How can I help?",
                     "message_id": "m1", "created_timestamp": 0},
                ],
            })
        return httpx.Response(404, json={"error": "no handler"})

    return httpx.MockTransport(respond)


def _make_connector(history: list[httpx.Request]) -> RetellConnector:
    client = httpx.AsyncClient(
        transport=_handler(history),
        base_url="https://api.retellai.test",
        headers={"Authorization": "Bearer test-key"},
    )
    cfg = ProviderSpec(name="retell", api_key="test-key", agent_id="agent_test")
    return RetellConnector(cfg, http_client=client)


def test_create_chat_then_send_turn() -> None:
    async def run() -> None:
        history: list[httpx.Request] = []
        conn = _make_connector(history)
        case = TestCase(id="t1")
        session = await conn.start_session(case)
        reply = await session.send_user_turn("Hello")
        assert reply.role == Role.AGENT
        assert "help" in (reply.text or "").lower()
        # Verify the right endpoints were hit, in the right order.
        paths = [r.url.path for r in history]
        assert paths == ["/create-chat", "/create-chat-completion"]
        summary = await session.end()
        assert summary.disconnect_reason == "completed"

    asyncio.run(run())


def test_tool_call_is_captured_in_summary() -> None:
    async def run() -> None:
        history: list[httpx.Request] = []
        conn = _make_connector(history)
        case = TestCase(id="t2")
        session = await conn.start_session(case)
        await session.send_user_turn("Hola, necesito una cita")
        await session.send_user_turn("Para el martes por la mañana")
        summary = await session.end()
        assert any(t["name"] == "get_available_slots"
                   for t in summary.tool_invocations)
        # transcript has agent + tool events
        roles = [e.role for e in session.transcript]
        assert Role.AGENT in roles
        assert Role.TOOL in roles

    asyncio.run(run())


def test_missing_agent_id_raises() -> None:
    with pytest.raises(ValueError, match="agent_id"):
        RetellConnector(ProviderSpec(name="retell", api_key="x"))


def test_missing_api_key_raises() -> None:
    with pytest.raises(ValueError, match="api_key"):
        # No http_client and no api_key -> must blow up
        RetellConnector(ProviderSpec(name="retell", agent_id="agent_x"))
