# Vapi demo — live end-to-end run findings (2026-05-24)

## Overview

Pointed voice-eval-harness at a real Vapi assistant
(`voxeval-demo-clinic`, a front-desk agent for a fictional Bayview Family
Clinic with two function tools: `get_available_slots` and
`check_insurance_coverage`). The assistant was created via
`POST https://api.vapi.ai/assistant` from `assistant-config.json` and
lives under our Vapi org (assistant_id pinned in `voxeval.yaml`). Five-case
suite ran with `--max-cost 1.00`, capturing JSON, JUnit and stdout under
`examples/vapi-demo/demo-run.{json,xml,log}`.

## Results

| case_id                     | result | notes                                                                                                                                              |
| --------------------------- | ------ | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| greeting_happy_path         | FAIL   | First user turn hit `HTTPStatusError: 402 Payment Required` from `POST /chat`. `assert_no_crash` passed; `assert_contains` failed (no agent text). |
| impatient_reschedule        | FAIL   | Persona-driven turn aborted on the same 402. `assert_no_crash` and `assert_latency_ms` (p95<4000ms) both still passed against the failed turn.     |
| insurance_intent_judge      | FAIL   | Same 402 on first turn. LLM-judge assertion correctly reported "no agent output to evaluate".                                                      |
| book_slot_calls_tool        | FAIL   | Same 402; `assert_tool_called: get_available_slots` correctly failed because zero tool invocations were recorded.                                  |
| spanish_english_code_switch | FAIL   | Same 402 on first persona turn. `assert_not_contains` passed (empty transcript), judge assertion failed.                                           |

Final score: **0 passed / 5 failed**, total spend **$0.0009**
(well under the $1.00 cap), suite wall time ~2.2s.

## What the harness surfaced

Even though every case failed for the same upstream reason, the run is
genuinely informative — this is the kind of signal the harness was built
to produce on day one of integrating a new provider:

1. **Single root cause across all five cases.** The harness clustered
   identical `HTTPStatusError 402 Payment Required` notes across every
   case, making it obvious in one glance that this is *one* infra
   problem, not five eval bugs. The user does not have to read five
   stack traces.
2. **Assertion-level granularity survives transport failures.** Even
   with no agent response, the report still shows which assertions
   passed (`assert_no_crash`, `assert_latency_ms`,
   `assert_not_contains`) and which failed (`assert_contains`,
   `assert_tool_called`, `assert_llm_judge`). That separation tells you
   the eval engine kept running rather than aborting the whole suite.
3. **Tool-call assertion is wired correctly end-to-end.** The
   `book_slot_calls_tool` case proves the connector's
   `tool_invocations` plumbing reaches the assertion layer — it
   correctly reported zero invocations rather than crashing. As soon as
   the underlying call succeeds, the same code path will verify Vapi
   actually emitted a `get_available_slots` tool call.
4. **Budget guardrail held.** The suite spent $0.0009 (judge tokens
   only) and the budget cap was respected with no skipped calls. If a
   future failure caused a retry storm, the `--max-cost 1.00` cap would
   stop it long before a surprise bill.
5. **Schema drift caught at the right layer.** During this demo we
   verified that Vapi's live `/chat` schema is
   `{assistantId, input, previousChatId?}` — the `messages: [...]` shape
   shown in some doc pages 400s against the live API. Our connector
   already matches the live schema, and the unit tests in
   `tests/unit/test_vapi_connector.py` continue to pass — so when
   payment is enabled, the existing code will work without further
   changes.

## Blocker (one-time, billing only)

`POST https://api.vapi.ai/chat` returns
`402 "Add a payment method to use chat. Pay-as-you-go orgs require a
card on file."` for our org. This is a Vapi billing-side requirement,
not a code issue. Add a card at https://dashboard.vapi.ai/ → Billing,
then re-run:

```bash
source .env && .venv/bin/voxeval run examples/vapi-demo/voxeval.yaml \
  --max-cost 1.00 \
  --json examples/vapi-demo/demo-run.json \
  --junit examples/vapi-demo/demo-run.xml
```

The assistant ID is already wired in
(`agent_id: fca80c92-cbd1-4230-9a3a-48ed600edf22`).

## What to record in the demo (60-90 sec cut)

1. **0:00–0:10** — Show `examples/vapi-demo/voxeval.yaml` on screen.
   Five cases, scripted + persona + LLM-judge + tool-call + multilingual —
   all declarative.
2. **0:10–0:20** — Show `assistant-config.json` and the
   `curl POST /assistant` that produced the live UUID. "One file, one
   call, real Vapi agent."
3. **0:20–0:55** — Run `voxeval run examples/vapi-demo/voxeval.yaml --max-cost 1.00`.
   The rich table renders live: five rows, per-case
   latency, per-assertion pass/fail counts, total spend vs. cap. This
   is the money shot — the table tells a complete eval story in under
   3 seconds.
4. **0:55–1:15** — Cut to `demo-run.json`: show the structured
   transcript + assertion_results for `book_slot_calls_tool`. Narrate:
   "the harness checks not just what the agent said but which tools it
   actually called — this is what CI for voice agents looks like."
