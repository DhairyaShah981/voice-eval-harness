"""``voxeval pin-urls`` — companion to RTL-016.

Walks every tool URL and webhook URL in a Retell agent JSON, hits each one
with HEAD (falling back to GET if HEAD is rejected), and reports the
results. Optionally writes an ``urls.lock.json`` capturing each URL's
final status, content-type, and any redirects, so a future regression can
detect "this URL went 404 since Tuesday" without re-running a full suite.

Catches the ngrok dev-tunnel rot directly — if a tunnel went away over
the weekend, the agent will fail in production; pin-urls fails locally first.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

import httpx
import typer
from rich.console import Console
from rich.table import Table

console = Console()


def _collect_urls(agent: dict[str, Any]) -> list[tuple[str, str]]:
    """Return [(source_path, url), ...] for every URL we want to check."""
    out: list[tuple[str, str]] = []
    wh = agent.get("webhook_url")
    if isinstance(wh, str) and wh.startswith(("http://", "https://")):
        out.append(("$.webhook_url", wh))
    cf = agent.get("conversationFlow") or {}
    for i, t in enumerate(cf.get("tools") or []):
        if not isinstance(t, dict):
            continue
        url = t.get("url")
        if isinstance(url, str) and url.startswith(("http://", "https://")):
            tid = t.get("tool_id") or i
            out.append((f"tool[{tid}].url", url))
    return out


async def _check_one(client: httpx.AsyncClient, url: str) -> dict[str, Any]:
    t0 = time.monotonic()
    try:
        resp = await client.head(url, follow_redirects=True)
        if resp.status_code in (405, 501):
            resp = await client.get(url, follow_redirects=True)
    except httpx.RequestError as exc:
        return {"status_code": 0, "elapsed_ms": int((time.monotonic() - t0) * 1000),
                "error": f"{type(exc).__name__}: {exc}", "ok": False}
    elapsed = int((time.monotonic() - t0) * 1000)
    ok = 200 <= resp.status_code < 400
    return {
        "status_code": resp.status_code,
        "elapsed_ms": elapsed,
        "final_url": str(resp.url),
        "content_type": resp.headers.get("content-type", ""),
        "ok": ok,
    }


async def _run(agent_path: Path, lock_path: Path | None, timeout: float) -> int:
    try:
        agent = json.loads(agent_path.read_text())
    except json.JSONDecodeError as exc:
        console.print(f"[red]{agent_path} is not valid JSON: {exc}[/red]")
        return 1
    urls = _collect_urls(agent)
    if not urls:
        console.print(f"No URLs found in {agent_path}")
        return 0

    table = Table(title=f"voxeval pin-urls — {agent_path}", show_lines=False)
    table.add_column("Where")
    table.add_column("URL", overflow="fold")
    table.add_column("Status")
    table.add_column("Elapsed")

    failures = 0
    lock_entries: dict[str, dict[str, Any]] = {}
    async with httpx.AsyncClient(timeout=timeout) as client:
        results = await asyncio.gather(*(_check_one(client, u) for _, u in urls))
        for (path, url), res in zip(urls, results, strict=True):
            color = "green" if res["ok"] else "red"
            status_cell = (f"[{color}]{res.get('status_code', 0)}[/{color}]"
                           + (f" [red]{res.get('error', '')}[/red]"
                              if res.get('error') else ""))
            table.add_row(path, url, status_cell, f"{res['elapsed_ms']}ms")
            lock_entries[url] = {"source_path": path, **res}
            if not res["ok"]:
                failures += 1

    console.print(table)
    console.print(f"\n[bold]{len(urls) - failures}/{len(urls)} reachable[/bold]")
    if lock_path:
        lock_path.write_text(json.dumps({
            "agent": str(agent_path),
            "checked_at": int(time.time()),
            "urls": lock_entries,
        }, indent=2))
        console.print(f"Wrote lock file -> {lock_path}")

    return 1 if failures else 0


def run(
    agent_json: Path = typer.Argument(
        ..., exists=True, readable=True, dir_okay=False,
        help="Path to a Retell agent JSON whose tool URLs / webhook should be checked.",
    ),
    lock: Path | None = typer.Option(
        None, "--lock", help="Write a urls.lock.json snapshot.",
    ),
    timeout: float = typer.Option(8.0, "--timeout"),
) -> None:
    code = asyncio.run(_run(agent_json, lock, timeout))
    sys.exit(code)
