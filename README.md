# voice-eval-harness

> Voice AI has eaten phone calls. The eval tooling has not caught up.
>
> `voice-eval-harness` is the open-source eval harness for voice agents — Retell-first, Vapi next, every other platform via plugin. Lint your agent config before it crashes Retell's importer. Replay last week's failed prod calls as deterministic regression cases. Stress-test with adversarial caller personas. Verify your knowledge base is actually wired and answerable. Gate CI on pass-rate, latency, and cost.

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
![Status](https://img.shields.io/badge/status-alpha-orange.svg)

## Why this exists

If you've built voice agents on Retell, you have already lost time to:

- `is_transfer_cf` missing → "Cannot read properties of undefined" on import
- `parameters.required: []` → HTTP 400 on import
- `tool_id` refs that look right but point at nothing
- KB IDs left empty while the global prompt cheerfully references "KB doc 02"
- `language: "en-US"` silently blocking Spanish callers
- Hand-written test cases sitting in a JSON file that nothing ever runs
- ngrok dev tunnels rotting in production agent JSON

Existing closed-source platforms (Hamming, Cekura, Coval, Bluejay) solve some of this — for money, on their cloud. The only OSS option (LiveKit's `RunResult.expect.judge()`) only works for LiveKit-native agents. This project is the Promptfoo-equivalent for voice, and it runs locally.

## Install

```bash
pip install voice-eval-harness
voxeval --version
```

## Quick start

```bash
voxeval init --provider retell                # scaffold voxeval.yaml + .env.example
voxeval generate --agent agents/eva.json      # 🪄 auto-generate 20+ healthcare test cases from one agent JSON
voxeval lint agents/eva.json                  # 17-rule structural linter
voxeval pin-urls agents/eva.json --lock       # probe tool/webhook URLs; fails on ngrok rot
voxeval run --max-cost 0.50 --junit out.xml   # full eval suite with budget cap + CI report
voxeval diff main.json feature.json           # per-case regression diff (exits 1 on regression)
voxeval kb-coverage --kb 'kb/*.md'            # auto-Q&A your KB and verify agent answers
voxeval replay --since 7d                     # regression fixtures from last week's failed prod calls
voxeval audit --since 24h                     # score yesterday's prod calls against assert_* contracts
voxeval drift-watch --sample 20               # check cached LLM-judge verdicts for model drift
```

## New-clinic onboarding in 60 seconds

`voxeval generate` turns one agent JSON into a complete eval suite covering
every healthcare scenario you'd otherwise script by hand:

```bash
voxeval generate --agent agents/eva-scheduling.json --out voxeval.yaml
```

Output: a 20-30 case suite with **one happy-path test per tool the agent
declares** (auto-derived `assert_tool_called` + `assert_tool_shape` from the
JSONSchema parameters) plus 19 curated healthcare scenarios:

- New patient happy-path booking, returning-patient flow (no redundant intake)
- **Urgent symptom triage** — chest pain, stroke symptoms (FAST) → must escalate, not schedule
- **Insurance verification** — known plan (KB-driven), unknown plan (must hedge, not fabricate)
- **Provider preference** — caller asks for a doctor; agent must verify they exist
- Reschedule/cancel with tool-call enforcement
- **Wrong-number callers** — agent MUST NOT collect PHI
- After-hours queries, prescription refills (must defer)
- Transfer-to-human, referral inbound capture
- Spanish language drift detection
- 4 persona stress tests (impatient, accented, code-switching, KB-probing)

Real numbers from this repo's `examples/healthcare-clinic/`:

| Agent                                | Auto-generated cases |
|--------------------------------------|---------------------:|
| eva-scheduling (ENT)                 | **24** (5 tool-calls + 19 scenarios) |
| linda-scheduling (Endoscopy)         | **22** (3 tool-calls + 19 scenarios) |
| iris-en (Ophthalmology)              | **20** (1 tool-call + 19 scenarios)  |
| iris-en.prod (Cardiology)            | **20** (1 tool-call + 19 scenarios)  |
| router-agent (multilingual router)   | **17** (0 tool-calls + 17 scenarios) |

**Total: 103 test cases generated from 5 production agents — 5 commands, 0 hand-written YAML.**

## What's in v0.1

| Feature | What it catches |
|---|---|
| **Retell JSON linter** (RTL-001 – RTL-017) | 15 rules ported from a battle-tested validator + RTL-016 (ngrok URL rot) + RTL-017 (KB empty but referenced in prompts) |
| **Persona simulator** | 4 adversarial callers (impatient, accented, code-switching, KB-probing) with overridable Jinja prompts |
| **KB coverage analyzer** | Auto-generates Q&A from your markdown KB, verifies the agent can actually answer (LLM-judge or sentence-transformers backend) |
| **Production-call replay + audit** | Pulls failed calls from Retell logs, scrubs PHI (regex + optional Presidio), turns them into regression cases. `audit` scores yesterday's calls against your contracts. |
| **LLM-judge with budget guardrail** | Semantic intent checks; `--max-cost USD` ceiling refuses calls past the limit instead of burning past |
| **`assert_tool_shape`** | Runtime tool-args contract validator (type/enum/min/max/regex) |
| **`voxeval diff`** | Per-case regression diff between two runs or two YAMLs (exits 1 on regression — CI gate) |
| **`voxeval pin-urls`** | HEADs every tool/webhook URL, writes a lock file, fails on rot |
| **CI integration** | JUnit XML output, `report.json`, pre-commit hook, GitHub Action template |
| **Dashboard** | TypeScript / Next 15 / Recharts / Supabase under `dashboard/` |
| **Connectors** | Retell (text + audio), Vapi (full), Mock (deterministic), LiveKit / Pipecat / Bland (stubs) |

## Dashboard (TypeScript)

Lives at `dashboard/` — Next.js 15 + React 19 + Recharts + Supabase. Drag-and-drop a `report.json` produced by `voxeval run --json out.json` and it lights up: pass-rate sparkline per suite, per-case grid with transcript drawer, ingest API (`POST /api/runs` with Bearer auth). One-time setup: paste `dashboard/supabase/schema.sql` into your Supabase SQL editor, copy three env vars into `dashboard/.env.local`, `pnpm dev`. ~10 minutes from clone to live.

## v0.2 roadmap (post-v1.0)

- Insurance-acceptance fact matrix (healthcare-vertical assertion)
- Multi-judge cross-model evaluation
- Carbon-cost report
- Drift-watch with prompt replay (v1.0 ships verdict-distribution baseline only)
- LiveKit, Pipecat, Bland connectors with their native test framework integrations
- Diff view in the dashboard UI

## Real-world findings on day one

Pointed at the 8 most recent production Retell agents in a healthcare
voice-AI shop (15+ live agents across ENT, ophthalmology, cardiology):

| Agent                    | RTL fatals | RTL warnings | Notes |
|--------------------------|-----------:|-------------:|-------|
| linda-scheduling.json    | 0          | 0            | known-good baseline ✅ |
| eva-scheduling.local.json| 0          | 6            | 6× ngrok dev URLs baked in (would rot in prod) |
| iris-en.json             | 2          | 0            | missing is_transfer_cf + KB empty but referenced |
| iris-es.json             | 2          | 0            | same |
| iris-zh.json             | 2          | 0            | same |
| router-agent.json        | 4          | 0            | missing response_engine + CF required keys |
| stockton iris-en.prod    | 1          | 0            | KB empty but prompt references KB |
| stockton iris-en.dev     | 1          | 0            | same |

That's **13 fatal bugs across 6 of 8 agents** the linter would have caught
before any Retell import attempt — the exact "Cannot read properties of
undefined" crash from the team's bug history shows up in three Iris agents
right now.

## Caveats and limitations (v0.1)

- **Text-mode requires a Retell agent registered with `channel=chat`.** Voice
  agents return HTTP 422 ("Cannot start a chat session with selected agent")
  against `/create-chat`. In practice you either (a) create a parallel
  chat-channel agent in the Retell dashboard with the same prompt + tools
  for testing, or (b) wait for v0.2 audio-mode which calls the real PSTN
  number with cost guardrails.
- **LLM judge and KB generator are model-cost-bearing.** Default cache
  keeps repeat runs near-free; first run on a new suite + KB costs a few
  cents at gpt-4o-mini rates.
- **PHI scrubbing in `voxeval replay` is regex-only by default.** The
  optional `[phi]` extra adds Microsoft Presidio for stronger NER-based
  redaction. Always inspect `replay_cases/*.yaml` before committing them.

## License

Apache 2.0 — see [LICENSE](LICENSE).
