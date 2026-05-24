# healthcare-clinic — real eval suites for production Retell voice agents

These suites were designed against real production voice agents at a
healthcare voice-AI shop (15+ live agents across ENT, ophthalmology,
cardiology). Each YAML below is structured to do two things:

1. **Lint the agent JSON** (catches the structural bugs the linter found
   on day one — `is_transfer_cf` crashes, empty KB IDs, ngrok URL rot).
2. **Drive the agent through realistic multi-turn scenarios** (happy path,
   adversarial personas, multilingual switching, tool-call verification).

## Files

| File                         | Persona / use case                         |
|------------------------------|--------------------------------------------|
| `eva-ent-sd.yaml`            | ENT scheduling: insurance filter, urgent triage, returning patient |
| `linda-redding.yaml`         | Endoscopy screening: 9-field questionnaire, EHR write |
| `iris-cal-retina.yaml`       | Ophthalmology with mid-call language switch (en ↔ es ↔ zh) |
| `iris-cal-retina-router.yaml`| DTMF language router fallback when no key is pressed |
| `stockton-cardiology.yaml`   | Cardiac referral intake, emergency detection |

## Quick start

```bash
# from the repo root, with .env populated:
export $(grep -v '^#' .env | xargs)

# point at the agent JSON we want to lint + the live agent_id we want to run
voxeval lint examples/healthcare-clinic/agents/eva.json
voxeval run  examples/healthcare-clinic/eva-ent-sd.yaml
```

> **Text-mode caveat:** Retell text-chat requires the target agent be
> registered with `channel=chat`. Voice-channel agents return HTTP 422.
> See the main README "Caveats" section.

## What the agent_id placeholders mean

Each YAML uses `REPLACE_WITH_*_AGENT_ID` for the Retell agent_id. Drop
in the real agent ID from your `voice_agent_configs` table (or the
Retell dashboard). The `agent_json` path points at the local file the
linter pre-flight reads — pre-flight runs even without a key.
