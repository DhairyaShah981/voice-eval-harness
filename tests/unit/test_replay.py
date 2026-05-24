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
    """list_failed_calls hits /v3/list-calls AND enriches each call via
    /v2/get-call/{id} to pull the transcript (the list view is metadata-only)."""
    paths_hit: list[str] = []
    bodies_sent: list[bytes] = []

    def respond(request: httpx.Request) -> httpx.Response:
        paths_hit.append(request.url.path)
        bodies_sent.append(request.content)
        if request.url.path == "/v3/list-calls":
            return httpx.Response(200, json={
                "pagination_key": None,
                "has_more": False,
                "items": [
                    {"call_id": "c1", "disconnection_reason": "user_hangup"},
                ],
            })
        if request.url.path.startswith("/v2/get-call/"):
            return httpx.Response(200, json={
                "call_id": "c1",
                "transcript": "User: hi\nAgent: oh no\n",
                "disconnection_reason": "user_hangup",
            })
        return httpx.Response(404)

    async def run() -> None:
        client = httpx.AsyncClient(
            transport=httpx.MockTransport(respond),
            base_url="https://api.retell.test",
            headers={"Authorization": "Bearer test"},
        )
        items = await list_failed_calls(
            since="3d", statuses=["user_hangup"], limit=5, http_client=client,
        )
        await client.aclose()
        assert len(items) == 1
        assert items[0]["call_id"] == "c1"
        # transcript came from the /v2/get-call enrichment step
        assert "User: hi" in items[0].get("transcript", "")
        assert "/v3/list-calls" in paths_hit
        assert any(p.startswith("/v2/get-call/") for p in paths_hit)
        # Verify the typed-filter shape made it onto the wire.
        list_body = next(b for p, b in zip(paths_hit, bodies_sent, strict=True)
                         if p == "/v3/list-calls")
        assert b'"type":"enum"' in list_body
        assert b'"op":"in"' in list_body

    asyncio.run(run())
