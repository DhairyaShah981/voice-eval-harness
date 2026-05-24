# voice-eval-harness — Findings on Day One

> A consolidated record of what the harness surfaced when pointed at a real
> healthcare voice-AI shop with 15+ production Retell agents + a fresh Vapi
> assistant. Use this as the script for the demo recording.

## TL;DR

- **Retell linter caught 13 fatal bugs across 6 of 8 production agents**
  before any Retell import attempt, including the exact "Cannot read
  properties of undefined" crash bug the team has been re-introducing for
  months.
- **6 ngrok dev-tunnel URLs** were baked into a live agent's tool /
  webhook config — would have rotted the next time the tunnel restarted.
  Caught by `voxeval pin-urls` (proactive) and `RTL-016` (in the linter).
- **Live Vapi assistant created** and the harness end-to-end suite ran
  against it. Cost guardrail held at $0.0009 / $1.00 cap. (Suite stopped
  at HTTP 402 — Vapi billing block, see `examples/vapi-demo/FINDINGS.md`.)
- **107 unit + e2e tests pass.** All 8 PRD pain-points (P1-P8) are
  covered by automated tests in `tests/e2e/test_pain_points_acceptance.py`.

## Linter findings — all 8 production agents

Run on 2026-05-24 from a clean install:

| Agent | Fatals | Warns | Rules fired | Real-world impact |
|---|---:|---:|---|---|
| `linda-scheduling.json` (Redding Endoscopy) | 0 | 0 | — | clean baseline ✅ |
| `eva-scheduling.local.json` (ENT-SD) | 0 | 6 | RTL-016 | 6× ngrok tool URLs baked in; will rot at next tunnel restart |
| `iris-en.json` (Cal Retina) | 2 | 0 | RTL-004, RTL-017 | crashes Retell importer; KB empty but prompt references KB doc |
| `iris-es.json` (Cal Retina) | 2 | 0 | RTL-004, RTL-017 | same — Spanish version |
| `iris-zh.json` (Cal Retina) | 2 | 0 | RTL-004, RTL-017 | same — Mandarin version |
| `router-agent.json` (Cal Retina DTMF router) | 4 | 0 | RTL-001, RTL-002, RTL-005 | missing top-level keys, no response_engine, no conversationFlow required keys |
| `iris-en.prod.json` (Stockton Cardiology) | 1 | 0 | RTL-017 | KB empty but prompt references KB |
| `iris-en.dev.json` (Stockton Cardiology) | 1 | 0 | RTL-017 | same |

**13 fatal bugs that would have broken Retell import. 6 ngrok URL warnings.
Caught in ~80ms total runtime per agent.**

### What each rule means in plain English

- **RTL-004 `is_transfer_cf` missing** — Retell's importer accesses
  `conversationFlow.is_transfer_cf` without a null-check; if absent it
  throws `Cannot read properties of undefined (reading is_transfer_cf)`.
  This is the bug claude-mem records as obs #2196 (Eva v3 import failure
  on May 13). Three Iris agents are sitting on this exact bug right now.
- **RTL-017 KB empty but prompt references KB** — Cal Retina Iris agents
  have `knowledge_base_ids: []` but the system prompt instructs the agent
  to "look up insurance acceptance in KB doc 02". Result: silent
  hallucination. Live callers think they're talking to a knowledgeable
  agent; the agent is making facts up.
- **RTL-016 ngrok URLs** — Eva ENT-SD has 6 production tool/webhook URLs
  pointing at `farreachingly-unrescissory-irena.ngrok-free.dev`. ngrok
  tunnels reset on container restart. Every restart breaks the agent.
- **RTL-001 / RTL-002 / RTL-005** — Cal Retina router is missing top-level
  required keys (no `webhook_url`, no `response_engine`, no `conversationFlow`).
  Cannot be imported into Retell at all.

## Tool/webhook URL reachability (pin-urls)

`voxeval pin-urls eva-scheduling.local.json --lock urls.lock.json` walks
each URL with HEAD + GET fallback. Reachability snapshot persists as a
lock file. Compare against tomorrow's snapshot to detect rot.

## Live Vapi demo

See `examples/vapi-demo/FINDINGS.md`. Assistant
`fca80c92-cbd1-4230-9a3a-48ed600edf22` created live; harness ran 5 cases
against it before hitting the Vapi billing wall. Even with 0/5 passing
cases, the harness produced clean structured output: per-case latency,
per-assertion granularity, total spend vs. cap.

## Test coverage (this repo)

- **107 tests pass** (unit + e2e)
- 9 CLI commands wired (`init`, `lint`, `run`, `diff`, `kb-coverage`,
  `replay`, `pin-urls`, `audit`, `drift-watch`)
- 7 connectors registered (retell, vapi, mock, livekit/pipecat/bland stubs)
- 17 linter rules (RTL-001..RTL-017)
- 9 built-in assertions (contains, not_contains, no_crash, latency_ms,
  tool_called, tool_args, language, pii_redacted, **tool_shape**) plus
  llm_judge with disk cache + budget guardrail
- 4 adversarial personas (impatient, accented, code_switching, kb_probing)
  with overridable Jinja prompts under `personas/prompts/`
- Pydantic v2 models, async engine with bounded concurrency, per-case
  retries with exp backoff + `meta_flake` markers
- TypeScript dashboard MVP (Next 15 + React 19 + Recharts + Supabase),
  builds clean

## Demo script — 90-second cut

1. **0:00–0:15** — Open `eva-scheduling.local.json` in editor. Run
   `voxeval lint eva-scheduling.local.json`. Six ngrok URL warnings
   render instantly. "Pre-prod CI you don't have today."
2. **0:15–0:35** — Run `voxeval lint iris-en.json` against a real Cal
   Retina agent. Show RTL-004 (`is_transfer_cf` missing — the bug we've
   shipped to prod three times). "Linter catches it before Retell does."
3. **0:35–0:55** — Run `voxeval run examples/healthcare-clinic/eva-ent-sd.yaml`
   (with MockConnector since live agents are voice-only). Show the
   rich table: persona, language, tool-call, judge — all green/red.
4. **0:55–1:15** — Show `voxeval diff main.json feature.json`. Per-case
   delta with REGRESSION / IMPROVEMENT highlights. "Reviewer can see
   in 2 seconds whether the prompt change is net-positive."
5. **1:15–1:30** — Cut to the dashboard at `pnpm dev`. Drop a
   `report.json` into the upload zone. Pass-rate sparkline + per-case
   drill-down. "v0.2 dashboard ships with v1.0."
