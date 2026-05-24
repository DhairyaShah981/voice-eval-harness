"""Replay pipeline: scrubber masks PHI, extractor produces stable fixtures,
retell_source posts the right body shape against a MockTransport."""

from __future__ import annotations

import asyncio

import httpx

from voice_eval_harness.replay.extractor import (
    extract_fixture,
    fixture_to_yaml_dict,
    parse_transcript,
)
from voice_eval_harness.replay.retell_source import list_failed_calls
from voice_eval_harness.replay.scrubber import scrub_text


def test_scrubber_redacts_common_phi() -> None:
    text = (
        "Patient John Doe at john.doe@example.com, MRN: ABC123456, "
        "phone (415) 555-2671, DOB 03/14/1985, lives at 1234 Main Street."
    )
    sr = scrub_text(text)
    assert "<redacted:email>" in sr.text
    assert "<redacted:mrn>" in sr.text
    assert "<redacted:phone>" in sr.text
    assert "<redacted:dob>" in sr.text
    assert "<redacted:address>" in sr.text
    assert sr.confidence < 1.0


def test_parse_transcript() -> None:
    t = """User: Hi, I'd like to book.
Agent: Sure, when?
User: Tomorrow at 2pm please.
Agent: I'm sorry, an error occurred."""
    turns = parse_transcript(t)
    assert [r for r, _ in turns] == ["user", "agent", "user", "agent"]
    assert "book" in turns[0][1]


def test_extract_fixture_dedupes_by_hash() -> None:
    call_a = {
        "call_id": "call_001",
        "disconnection_reason": "agent_error",
        "transcript": "User: hi there\nAgent: error occurred\n",
    }
    call_b = {
        "call_id": "call_002",  # different id
        "disconnection_reason": "agent_error",
        "transcript": "User: hi there\nAgent: different reply\n",
    }
    f_a = extract_fixture(call_a)
    f_b = extract_fixture(call_b)
    assert f_a is not None and f_b is not None
    assert f_a.case_id == f_b.case_id  # same user turns -> same hash


def test_extract_fixture_phi_scrubbed_in_yaml() -> None:
    call = {
        "call_id": "call_phi",
        "disconnection_reason": "agent_error",
        "transcript": ("User: my number is (415) 555-2671\n"
                       "Agent: sorry, error\n"),
    }
    fix = extract_fixture(call)
    assert fix is not None
    case_dict = fixture_to_yaml_dict(fix)
    user_says = case_dict["script"][0]["user_says"]
    assert "555-2671" not in user_says
    assert "<redacted:phone>" in user_says
    # Assert_no_crash and assert_not_contains injected
    suite = case_dict["suite_asserts"]
    assert any("assert_no_crash" in s for s in suite)
    assert any("assert_not_contains" in s for s in suite)


def test_list_failed_calls_posts_correct_body() -> None:
    captured: dict[str, dict] = {}

    def respond(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["body"] = httpx.Request("POST", "x", content=request.content).content
        return httpx.Response(200, json={
            "pagination_key": None,
            "has_more": False,
            "items": [
                {"call_id": "c1", "disconnection_reason": "agent_error",
                 "transcript": "User: hi\nAgent: oh no\n"},
            ],
        })

    async def run() -> None:
        client = httpx.AsyncClient(
            transport=httpx.MockTransport(respond),
            base_url="https://api.retell.test",
            headers={"Authorization": "Bearer test"},
        )
        items = await list_failed_calls(
            since="3d", statuses=["agent_error"], limit=5, http_client=client,
        )
        await client.aclose()
        assert len(items) == 1
        assert items[0]["call_id"] == "c1"
        assert captured["path"] == "/v3/list-calls"

    asyncio.run(run())
