# Changelog

## v1.0.0 — 2026-05-24

First production-ready release. Closes every gap in the PRD and the review.

### CLI surface (9 commands)
- `voxeval init` — project scaffold
- `voxeval lint` — 17-rule Retell agent JSON linter
- `voxeval run` — eval suite runner with `--max-cost`, `--junit`, `--json`, `--allow-audio`, `--skip-lint`
- `voxeval diff` — file-vs-file or run-vs-run regression diff (exits 1 on regressions for CI)
- `voxeval kb-coverage` — auto-generate Q&A from markdown KB, verify agent answers (LLM-judge or sentence-transformers backend)
- `voxeval replay` — pull failed prod calls, PHI-scrub, write deduped fixture YAMLs
- `voxeval pin-urls` — probe every tool/webhook URL, write a lock file, fail on rot
- `voxeval audit` — score the last N production calls against suite assertions
- `voxeval drift-watch` — re-check cached LLM-judge verdicts for model-snapshot drift

### Connectors
- `retell` — text-mode (`/create-chat`) and audio-mode (`/create-phone-call`, gated by `--allow-audio`)
- `vapi` — text-mode (`/chat` with `previousChatId` chaining), verified against live API
- `mock` — deterministic in-process connector for self-tests
- `livekit`, `pipecat`, `bland` — v0.1 stubs with clear NotImplementedError messages

### Assertions
- `contains`, `not_contains`, `no_crash`, `latency_ms`, `tool_called`, `tool_args`
- `language` (heuristic v0.1)
- `pii_redacted` (regex baseline)
- **`tool_shape`** — runtime contract validator for tool args (type/in/min/max/regex/allow_extra)
- `llm_judge` — pinned model snapshot, disk cache keyed by sha1(prompt+model), budget tracker

### Linter rules (17)
- RTL-001…RTL-015 — ported from the source-of-truth `validate_retell_agent.py`
- RTL-016 — ngrok dev URL scan (catches tool URL rot)
- RTL-017 — KB empty but referenced in prompt (catches silent RAG hallucination)
- Pre-commit hook at `.pre-commit-hooks.yaml`; GitHub Action template at `examples/.github/workflows/voxeval.yml`

### Engine
- Async with bounded concurrency
- Per-case retries with exp backoff; `meta_flake` marker on partial pass
- `start_session` failures caught and reported (was an unhandled exception in v0.1)
- Linter pre-flight on `provider.agent_json`; aborts on RTL fatals (override with `--skip-lint`)
- `BudgetTracker` enforces `--max-cost USD`; judge calls past the ceiling return `skipped_budget`
- `SuiteResult.cost_by_persona` per-persona spend breakdown

### Personas
- 4 built-in profiles with Jinja templates under `personas/prompts/` (user override: drop a file at `./personas/prompts/<type>.jinja`)

### KB
- Header-based markdown chunker (no langchain dep)
- Q/A generator with verification pass; sha1-keyed JSONL cache
- Two matcher backends: `llm_judge` (default, accurate) and `sentence_transformers` (offline, opt-in via `[kb]` extra)

### Replay
- Retell `/v3/list-calls` source; window like `7d` / `24h` / `30m`
- PHI scrubber: regex pack (SSN, phone, email, MRN, DOB, address, URL) + optional Presidio NER via `[phi]` extra
- Stable hash-derived case IDs; dedupes same-content fixtures across different `call_ids`
- Default `.gitignore` covers `replay_cases/`

### Reports
- Rich terminal table (default)
- JUnit XML for CI integration
- Full `SuiteResult` JSON for downstream tooling

### Dashboard (v0.2 in this repo)
- Next.js 15 + React 19 + TypeScript + Tailwind + Recharts
- Supabase schema + RLS at `dashboard/supabase/schema.sql`
- `POST /api/runs` Bearer-authed ingest, `GET /api/runs[/:id]`
- Runs index with pass-rate sparkline; run detail with case grid + transcript drawer
- ~10 minutes from clone to live with a real Supabase project

### Tests
- 107 passing (unit + e2e + parity)
- E2E acceptance test covers all 8 PRD pain points (P1–P8) — gating ship criterion
- Linter parity test against the vendored legacy validator
- httpx.MockTransport coverage for Retell text-mode, Retell audio-mode, Vapi

### Real-world findings
- See `FINDINGS.md` (root) and `examples/vapi-demo/FINDINGS.md` for the
  live results — 13 fatal bugs and 6 warnings caught across 8 production
  agents on day one.

---

## v0.1.1 — 2026-05-24

- Added `--max-cost`, retries, linter pre-flight, JSON report writer,
  pre-commit hook, GitHub Action template, `voxeval pin-urls`,
  README naming fix (RTL-001..RTL-017).

## v0.1.0 — 2026-05-24

- Initial scaffold (M1–M7): linter, core engine, MockConnector, Retell
  text-mode connector, LLM judge, persona simulator, KB coverage analyzer,
  production replay, VapiConnector, JUnit reporter. 74 tests passing.
