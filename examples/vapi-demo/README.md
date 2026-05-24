# Vapi demo — `voice-eval-harness` ↔ Vapi assistant

A 5-case suite that drives a real Vapi assistant via `POST /chat` and runs the
same eval primitives we use in healthcare prod: persona simulation, LLM-judge
assertions, tool-call assertions, multilingual code-switching.

## 30-second setup

1. **Create the assistant.** Copy `assistant-config.json` into the Vapi dashboard
   (Assistants → New → "from JSON"), or:
   ```bash
   curl -X POST https://api.vapi.ai/assistant \
     -H "Authorization: Bearer $VAPI_API_KEY" \
     -H "Content-Type: application/json" \
     -d @examples/vapi-demo/assistant-config.json
   ```
   Copy the returned `id` (a UUID).

2. **Wire the suite.** In `voxeval.yaml`, replace `REPLACE_WITH_VAPI_ASSISTANT_ID`
   with the UUID from step 1. Make sure `VAPI_API_KEY` is in the repo-root `.env`
   or your shell.

3. **Run.**
   ```bash
   voxeval run examples/vapi-demo/voxeval.yaml
   ```

## What this exercises

| Case | What it shows |
|---|---|
| `greeting_happy_path` | Smoke + `assert_contains` against a real Vapi turn |
| `impatient_reschedule` | Persona simulator (impatient) + latency budget + LLM judge |
| `insurance_intent_judge` | Semantic intent check via LLM-judge — catches hallucinated coverage answers |
| `book_slot_calls_tool` | `assert_tool_called` against the `get_available_slots` function tool |
| `spanish_english_code_switch` | `code_switching` persona for multilingual robustness |

See the [main README](../../README.md) for the full assertion grammar and persona
catalog.
