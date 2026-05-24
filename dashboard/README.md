# voice-eval-harness dashboard (v0.2)

Next.js 15 + Recharts + Supabase MVP that ingests `report.json` produced by
`voxeval run --json out.json` and renders runs, cases, and transcripts.

## Quickstart

```bash
pnpm install
cp .env.example .env.local   # fill in Supabase URL/keys, or leave blank for local mode
pnpm dev                     # http://localhost:3000
```

In local mode (no env vars set), drag a `report.json` onto the dropzone and it
will parse + render in-memory only.

## Wiring to Supabase

1. Create a project at supabase.com.
2. In the SQL editor, paste `supabase/schema.sql` and run it.
3. Copy the project URL + anon + service-role keys into `.env.local`.
4. Set `RUNS_INGEST_TOKEN` to a secret, then `POST` reports:

```bash
curl -X POST http://localhost:3000/api/runs \
  -H "Authorization: Bearer $RUNS_INGEST_TOKEN" \
  -H "Content-Type: application/json" \
  --data @report.json
```

## Build

```bash
pnpm build
```
