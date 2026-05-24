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
voxeval init --provider retell      # scaffolds voxeval.yaml + .env.example
voxeval lint agents/my-agent.json   # structural linter (catches all known import-breaking bugs)
voxeval run                         # full eval suite
voxeval replay --since 7d           # regression cases from your last week of failed prod calls
voxeval kb-coverage --kb ./kb       # is your knowledge base actually answerable?
```

## What's in v0.1

| Feature | What it catches |
|---|---|
| **Retell JSON linter** (R001–R015) | Every known Retell import failure, plus ngrok URL rot and KB-empty-but-referenced |
| **Persona simulator** | Adversarial callers: impatient, accented, code-switching, KB-probing |
| **KB coverage analyzer** | Auto-generates Q&A from your markdown KB, verifies the agent can actually answer |
| **Production-call replay** | Pulls failed calls from Retell logs, scrubs PHI, turns them into regression cases |
| **LLM-judge assertions** | Semantic intent checks, not brittle keyword matching |
| **CI integration** | JUnit XML output, pre-commit hook, GitHub Action template |
| **Connectors** | Retell (full), Vapi (full), LiveKit / Pipecat / Bland (stubs) |

## v0.2 roadmap

- React + Recharts dashboard backed by Supabase
- LiveKit, Pipecat, Bland connectors fully implemented
- Audio-mode (real WebRTC / PSTN) with cost guardrails
- Multi-judge cross-model evaluation
- Per-test cost + carbon report

## License

Apache 2.0 — see [LICENSE](LICENSE).
