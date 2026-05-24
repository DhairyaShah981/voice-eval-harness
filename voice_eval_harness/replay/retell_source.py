"""Pull recent failed calls from Retell's /v3/list-calls endpoint.

NOTE: ``/v3/list-calls`` returns metadata only — the ``transcript`` field
is NOT in the list response. To get the full conversation, we call
``GET /get-call/{call_id}`` per call after the list returns. Concurrent
via a bounded semaphore.
"""

from __future__ import annotations

import asyncio
import os
import re
import time
from typing import Any

import httpx

DEFAULT_BASE_URL = "https://api.retellai.com"

_SINCE_RE = re.compile(r"^(\d+)([smhd])$")


def _parse_since(since: str) -> int:
    """Turn '7d' / '24h' / '30m' into a unix-ms timestamp ``after``."""
    m = _SINCE_RE.match(since.strip())
    if not m:
        raise ValueError(f"--since must look like '7d', '24h', '30m'; got {since!r}")
    n = int(m.group(1))
    unit = m.group(2)
    secs = n * {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]
    return int((time.time() - secs) * 1000)


async def _enrich_with_transcripts(
    client: httpx.AsyncClient, calls: list[dict[str, Any]],
    *, concurrency: int = 8,
) -> list[dict[str, Any]]:
    """For each call summary, fetch GET /get-call/{id} to pull the full
    transcript. Drops calls that no longer exist (404 / deleted)."""
    sem = asyncio.Semaphore(concurrency)

    async def fetch_one(call: dict[str, Any]) -> dict[str, Any] | None:
        cid = call.get("call_id")
        if not cid:
            return None
        async with sem:
            r = await client.get(f"/v2/get-call/{cid}")
        if r.status_code == 404:
            return None
        if not r.is_success:
            return None
        # Merge the detail payload over the list-view summary.
        detail = r.json()
        return {**call, **detail}

    results = await asyncio.gather(*(fetch_one(c) for c in calls))
    return [r for r in results if r is not None]


async def list_failed_calls(
    *,
    api_key: str | None = None,
    since: str = "7d",
    statuses: list[str] | None = None,
    limit: int = 25,
    http_client: httpx.AsyncClient | None = None,
    base_url: str | None = None,
    enrich_transcripts: bool = True,
) -> list[dict[str, Any]]:
    """Fetch up to ``limit`` calls in the given window with the given
    disconnection reasons. Returns the raw call objects from Retell."""
    api_key = api_key or os.environ.get("RETELL_API_KEY", "")
    if not api_key and http_client is None:
        raise ValueError("RETELL_API_KEY env var or http_client= required")
    # `statuses=None`  → fall back to a sensible failure-flavor default.
    # `statuses=[]`    → explicit "no filter, pull every call in window".
    # Default values use Retell's real enum (some docs are misleading —
    # ``error_user_not_joined``/``no_answer`` are NOT valid values).
    if statuses is None:
        statuses = ["dial_no_answer", "dial_busy", "voicemail_reached",
                    "inactivity", "max_duration_reached"]
    after = _parse_since(since)

    close_client = False
    if http_client is None:
        http_client = httpx.AsyncClient(
            base_url=base_url or DEFAULT_BASE_URL,
            headers={"Authorization": f"Bearer {api_key}",
                     "Content-Type": "application/json"},
            timeout=httpx.Timeout(30.0),
        )
        close_client = True

    # Retell v3 typed-filter shape: {"type": "enum", "op": "in", "value": [...]}
    # for enums, and {"type": "number", "op": "gt", "value": <ms>} for numerics.
    # If the caller passes statuses=[] explicitly, skip the filter entirely
    # (broadest possible window).
    filter_criteria: dict[str, Any] = {
        "start_timestamp": {"type": "number", "op": "gt", "value": after},
    }
    if statuses:
        filter_criteria["disconnection_reason"] = {
            "type": "enum", "op": "in", "value": list(statuses),
        }

    try:
        body = {
            "limit": min(limit, 1000),
            "sort_order": "descending",
            "filter_criteria": filter_criteria,
        }
        resp = await http_client.post("/v3/list-calls", json=body)
        if not resp.is_success:
            raise RuntimeError(
                f"Retell /v3/list-calls returned HTTP {resp.status_code}: "
                f"{resp.text[:400]}  (body sent: {body!r})"
            )
        payload = resp.json()
        items = payload.get("items") or []
        items = items[:limit]
        # /v3/list-calls is metadata-only — transcripts come from /get-call.
        if enrich_transcripts and items:
            items = await _enrich_with_transcripts(http_client, items)
        return items
    finally:
        if close_client:
            await http_client.aclose()
