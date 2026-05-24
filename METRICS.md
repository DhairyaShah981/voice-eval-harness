# voice-eval-harness — Real Eval Metrics (2026-05-24)

These are not synthetic numbers. They were generated today by pointing
`voxeval` at real production agent JSONs in the user's healthcare
voice-AI stack, plus a comprehensive demo suite exercising every
assertion type. All commands shown below are reproducible from a clean
clone of the repo.

---

## 1. Linter findings — 8 production Retell agents

Command: `voxeval lint <agent.json> --format json` (runs in ~80ms per agent).

| Agent | Fatals | Warns | Rule(s) fired | Production impact |
|---|---:|---:|---|---|
| `linda-scheduling.json` (Redding Endoscopy) | **0** | **0** | — | clean baseline ✅ |
| `eva-scheduling.local.json` (ENT-SD) | 0 | **6** | RTL-016 | 6× ngrok URLs baked into webhook + 5 tool URLs |
| `iris-en.json` (Cal Retina) | **2** | 0 | RTL-004, RTL-017 | `is_transfer_cf` missing → Retell import crash; KB empty but prompt references KB doc |
| `iris-es.json` (Cal Retina) | **2** | 0 | RTL-004, RTL-017 | same — Spanish version |
| `iris-zh.json` (Cal Retina) | **2** | 0 | RTL-004, RTL-017 | same — Mandarin version |
| `router-agent.json` (Cal Retina DTMF router) | **4** | 0 | RTL-001, RTL-002, RTL-005 | missing `conversationFlow`, wrong `response_engine.type` (`retell-llm` vs `conversation-flow`), missing required CF keys |
| `iris-en.prod.json` (Stockton Cardiology) | **1** | 0 | RTL-017 | KB empty but prompt references KB |
| `iris-en.dev.json` (Stockton Cardiology) | **1** | 0 | RTL-017 | same |

**Aggregate: 12 fatal bugs + 6 warnings across 6 of 8 agents. Total
lint runtime: ~640ms.** All caught locally, before any Retell import
attempt or live call.

### Top rules by hit count

| Rule | Hits | What it catches |
|---|---:|---|
| RTL-017 (KB empty but referenced) | 5 | Silent RAG hallucination — prompt references KB, agent has no KB wired |
| RTL-016 (ngrok dev URL) | 6 | Tool/webhook URL rot at next tunnel restart |
| RTL-004 (`is_transfer_cf` missing) | 3 | "Cannot read properties of undefined" at Retell import |
| RTL-002 (response_engine shape) | 2 | wrong `type` or missing `version` |
| RTL-001 (top-level keys) | 1 | missing `webhook_url` / `voice_id` / etc. |
| RTL-005 (CF required keys) | 1 | missing `nodes` / `start_node_id` / `tools` |

---

## 2. URL reachability — Eva ENT-SD (live HEAD probe)

Command: `voxeval pin-urls eva-scheduling.local.json --lock urls.lock.json`

| URL location | Status | Elapsed |
|---|---:|---:|
| `$.webhook_url` (post-call webhook) | **405** | 303 ms |
| `tool[check-availability].url` | **405** | 300 ms |
| `tool[book-appointment].url` | **405** | 289 ms |
| `tool[find-appointment].url` | **405** | 287 ms |
| `tool[cancel-appointment].url` | **405** | 283 ms |
| `tool[check-eligibility].url` | **405** | 283 ms |

**0 of 6 ngrok URLs idempotently reachable (HEAD/GET returns 405).**
HTTP 405 means the tunnel is up but accepts POST only — fine for the live
Retell agent at runtime, but it means you have no idempotent health
check. The first time the ngrok tunnel reboots (and the URL changes),
production will silently break with no monitoring signal. Lock-file
snapshot at `/tmp/eva-urls.lock.json` lets you compare against tomorrow.

---

## 3. Comprehensive eval suite — `examples/metrics-demo/voxeval.yaml`

A 10-case suite exercising every assertion type and persona on
`MockConnector`. Three cases are **intentional FAILs** that prove the
harness catches the right things.

Command: `voxeval run examples/metrics-demo/voxeval.yaml --json examples/metrics-demo/report.json`

| Case | Result | Notes |
|---|---|---|
| `greeting_smoke` | ✅ PASS | assert_contains + assert_no_crash baseline |
| `insurance_filter_correct` | ✅ PASS | assert_not_contains caught no over-promising language |
| `insurance_filter_hallucinated` | ❌ **FAIL (intentional)** | assert_not_contains correctly caught "every" and "absolutely" — harness flagged the hallucination |
| `tool_call_books_slot` | ✅ PASS | assert_tool_called + assert_tool_shape with typed args, all green |
| `tool_call_bad_args` | ❌ **FAIL (intentional)** | assert_tool_shape correctly caught `day_of_week: "funday"` not in allowed enum |
| `spanish_caller_kept_in_spanish` | ✅ PASS | assert_language: es matched ("hola", "gracias", "supuesto") |
| `impatient_persona_resolves` | ✅ PASS | Persona simulator hit exit_pass marker ("confirmed") in 1 turn |
| `kb_probing_hedges_correctly` | ✅ PASS | Persona simulator hit exit_pass marker ("look that up") |
| `pii_leak_in_response` | ❌ **FAIL (intentional)** | assert_pii_redacted correctly caught SSN `123-45-6789` |
| `latency_within_budget` | ✅ PASS | assert_latency_ms p95<1500ms satisfied |

**7 pass / 3 fail (all 3 fails intentional).** Total spend: **$0.0000** (MockConnector, no API calls). Wall time: **52 ms** total for the suite.

The JSON report at `examples/metrics-demo/report.json` (4 KB) is ready
to upload to the dashboard.

---

## 4. Live Vapi assistant — current status

- Assistant `voxeval-demo-clinic` (id `fca80c92-cbd1-4230-9a3a-48ed600edf22`)
  created live in Vapi org `0db443f8-3d3c-4244-a7d6-d81339858f9b`.
- Model: `gpt-4o-mini`, voice: `11labs/burt`, transcriber: `deepgram/nova-2 multi`.
- Auth confirmed (GET `/assistant/{id}` → 200; `/call` returns 400 only when
  given a fake phone number, not 401 — billing is wired for phone calls).
- **`POST /chat` and `POST /chat/responses` still return HTTP 402** after
  card was added. The 402 message reads: *"Add a payment method to use
  chat. Pay-as-you-go orgs require a card on file."* Even with a card
  on file and a $1.00 max-cost cap, both endpoints refuse the request.

### Most likely cause + fix

Vapi accounts often have **multiple orgs** (personal + team). The card
was added to one org, but the assistant + API key live in
org `0db443f8-3d3c-4244-a7d6-d81339858f9b`. To unblock:

1. Open `https://dashboard.vapi.ai/`
2. Top-left org switcher → confirm `0db443f8-...` is selected
3. Settings → Billing & Add-Ons → confirm the card is on **this** org
4. If different, add the card to the assistant's org (or copy the API
   key from the org that has the card and re-run with the new key)
5. Re-run: `source .env && voxeval run examples/vapi-demo/voxeval.yaml --max-cost 1.00`

Once unblocked, the existing 5-case demo suite will produce real run
metrics (greeting, persona-driven, LLM-judge, tool-called,
multilingual) against a live Vapi assistant.

---

## 5. Test coverage in the harness itself

- **107 tests pass** (unit + e2e + linter parity)
- E2E acceptance test covers all 8 PRD pain points (P1–P8)
- 0 ruff errors, lint-clean across `voice_eval_harness/` and `tests/`

```
$ .venv/bin/pytest -q
.....................................................................  [ 67%]
...................................                                    [100%]
107 passed in 0.78s
```

---

## 6. How to reproduce these numbers

```bash
# from repo root, with .env populated
.venv/bin/voxeval lint examples/healthcare-clinic/agents/eva-scheduling.local.json
.venv/bin/voxeval pin-urls examples/healthcare-clinic/agents/eva-scheduling.local.json --lock /tmp/eva-urls.lock.json
.venv/bin/voxeval run examples/metrics-demo/voxeval.yaml --json examples/metrics-demo/report.json
.venv/bin/pytest -q
```

For the live Vapi run (after the org+card fix above):

```bash
source .env && voxeval run examples/vapi-demo/voxeval.yaml \
  --max-cost 1.00 \
  --json examples/vapi-demo/demo-run.json \
  --junit examples/vapi-demo/demo-run.xml
```
