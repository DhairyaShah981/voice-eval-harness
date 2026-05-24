"""pin-urls walks tool/webhook URLs and reports unreachable ones."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from voice_eval_harness.cli.pin_urls_cmd import _collect_urls


def test_collect_urls_finds_webhook_and_tools() -> None:
    fixture = (Path(__file__).resolve().parents[1] / "fixtures"
               / "agents" / "clean_minimal.json")
    agent = json.loads(fixture.read_text())
    urls = _collect_urls(agent)
    assert any(p == "$.webhook_url" for p, _ in urls)
    # clean_minimal has one custom tool with a https url.
    assert any("tool" in p for p, _ in urls)


def test_pin_urls_returns_status(tmp_path: Path) -> None:
    """We can't make real HTTP calls in unit tests; smoke-test _check_one
    against an in-process MockTransport."""
    import httpx

    from voice_eval_harness.cli.pin_urls_cmd import _check_one

    def respond(request: httpx.Request) -> httpx.Response:
        if "good" in str(request.url):
            return httpx.Response(200, headers={"content-type": "application/json"})
        return httpx.Response(404)

    async def go() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(respond),
        ) as client:
            r_ok = await _check_one(client, "https://example.test/good")
            r_404 = await _check_one(client, "https://example.test/bad")
            assert r_ok["ok"] and r_ok["status_code"] == 200
            assert not r_404["ok"] and r_404["status_code"] == 404
    asyncio.run(go())
