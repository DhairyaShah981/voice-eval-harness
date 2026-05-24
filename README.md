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
voxeval init --provider retell                # scaffolds voxeval.yaml + .env.example
voxeval lint agents/my-agent.json             # structural linter (catches all known import-breaking bugs)
voxeval pin-urls agents/my-agent.json --lock  # probe every tool/webhook URL; fails on ngrok rot
voxeval run --max-cost 0.50 --junit out.xml   # full eval suite with cost guardrail + CI report
voxeval replay --since 7d                     # regression cases from your last week of failed prod calls
voxeval kb-coverage --kb 'kb/*.md'            # is your knowledge base actually answerable?
```

## What's in v0.1

| Feature | What it catches |
|---|---|
| **Retell JSON linter** (RTL-001 – RTL-017) | 13 rules ported from a battle-tested validator, plus RTL-016 (ngrok URL rot) and RTL-017 (KB empty but referenced in prompts) |
| **Persona simulator** | Adversarial callers: impatient, accented, code-switching, KB-probing |
| **KB coverage analyzer** | Auto-generates Q&A from your markdown KB, verifies the agent can actually answer |
| **Production-call replay** | Pulls failed calls from Retell logs, scrubs PHI, turns them into regression cases |
| **LLM-judge assertions** | Semantic intent checks, not brittle keyword matching |
| **CI integration** | JUnit XML output, pre-commit hook, GitHub Action template |
| **Connectors** | Retell (full), Vapi (full), LiveKit / Pipecat / Bland (stubs) |

## v0.2 roadmap

- React + Recharts dashboard backed by Supabase (TypeScript)
- LiveKit, Pipecat, Bland connectors fully implemented
- Audio-mode (real WebRTC / PSTN) with cost guardrails
- Multi-judge cross-model evaluation
- Per-test cost + carbon report

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
