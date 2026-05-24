-- voice-eval-harness dashboard schema.
-- Run in the Supabase SQL editor (or via `supabase db push`).

create extension if not exists "pgcrypto";

create table if not exists runs (
  id             uuid primary key default gen_random_uuid(),
  suite_hash     text not null,
  workspace_id   uuid not null,
  started_at     timestamptz not null default now(),
  total_cost_usd numeric(10, 6) default 0,
  pass_count     int not null default 0,
  fail_count     int not null default 0,
  raw_report     jsonb not null
);

create index if not exists runs_workspace_started_idx
  on runs (workspace_id, started_at desc);

create table if not exists cases (
  id          uuid primary key default gen_random_uuid(),
  run_id      uuid not null references runs(id) on delete cascade,
  case_id     text not null,
  passed      boolean not null,
  duration_ms int not null,
  cost_usd    numeric(10, 6) default 0,
  error       text
);

create index if not exists cases_run_idx on cases (run_id);

create table if not exists assertions (
  id         uuid primary key default gen_random_uuid(),
  case_id_fk uuid not null references cases(id) on delete cascade,
  kind       text not null,
  passed     boolean not null,
  detail     text
);

create index if not exists assertions_case_idx on assertions (case_id_fk);

-- RLS — workspace_id is expected to equal auth.uid() for the MVP.
alter table runs       enable row level security;
alter table cases      enable row level security;
alter table assertions enable row level security;

drop policy if exists runs_select_own on runs;
create policy runs_select_own on runs
  for select using (workspace_id = auth.uid());

drop policy if exists runs_insert_own on runs;
create policy runs_insert_own on runs
  for insert with check (workspace_id = auth.uid());

drop policy if exists cases_select_own on cases;
create policy cases_select_own on cases
  for select using (
    exists (
      select 1 from runs r
      where r.id = cases.run_id and r.workspace_id = auth.uid()
    )
  );

drop policy if exists assertions_select_own on assertions;
create policy assertions_select_own on assertions
  for select using (
    exists (
      select 1
      from cases c
      join runs r on r.id = c.run_id
      where c.id = assertions.case_id_fk and r.workspace_id = auth.uid()
    )
  );
