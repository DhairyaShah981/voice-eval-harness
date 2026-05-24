"""Pull recent failed calls from Retell's /v3/list-calls endpoint."""

from __future__ import annotations

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


async def list_failed_calls(
    *,
    api_key: str | None = None,
    since: str = "7d",
    statuses: list[str] | None = None,
    limit: int = 25,
    http_client: httpx.AsyncClient | None = None,
    base_url: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch up to ``limit`` calls in the given window with the given
    disconnection reasons. Returns the raw call objects from Retell."""
    api_key = api_key or os.environ.get("RETELL_API_KEY", "")
    if not api_key and http_client is None:
        raise ValueError("RETELL_API_KEY env var or http_client= required")
    statuses = statuses or ["agent_error", "dial_busy", "error_user_not_joined"]
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

    try:
        resp = await http_client.post("/v3/list-calls", json={
            "limit": min(limit, 1000),
            "sort_order": "descending",
            "filter_criteria": {
                "disconnection_reason": statuses,
                "start_timestamp": {"after": after},
            },
        })
        resp.raise_for_status()
        payload = resp.json()
        items = payload.get("items") or []
        return items[:limit]
    finally:
        if close_client:
            await http_client.aclose()
