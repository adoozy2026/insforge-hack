-- Phase 1 of the self-improving extractor pool.
--
-- extractor_runs logs every successful browser-agent configurator pass so
-- we can later (a) decide when to ask Replicas to generate a deterministic
-- extractor for a domain, and (b) hand the cloud agent real samples to
-- learn from instead of synthetic ones.
--
-- extractor_jobs tracks the in-flight Replicas tasks so we don't re-fire
-- a generation while one is already running, and so the dashboard can
-- eventually surface "Replicas is writing an extractor for apple.com".
--
-- Both tables are append-mostly; we delete nothing on the live demo path.

create table if not exists extractor_runs (
  id              uuid primary key default gen_random_uuid(),
  domain          text not null,
  candidate_id    uuid references candidates(id) on delete set null,
  intent_id       uuid references intents(id) on delete set null,
  source_url      text not null,
  spec            jsonb not null default '{}'::jsonb,
  action_history  jsonb not null default '[]'::jsonb,
  extracted_facts jsonb not null default '{}'::jsonb,
  succeeded       boolean not null,
  created_at      timestamptz not null default now()
);
create index if not exists extractor_runs_domain_idx
  on extractor_runs(domain, created_at desc);
create index if not exists extractor_runs_succeeded_idx
  on extractor_runs(domain, succeeded);

do $$ begin
  create type extractor_job_status as enum (
    'queued', 'running', 'succeeded', 'failed'
  );
exception when duplicate_object then null; end $$;

create table if not exists extractor_jobs (
  id          uuid primary key default gen_random_uuid(),
  domain      text not null,
  replica_id  text,             -- nullable so we can insert before spawn
  status      extractor_job_status not null default 'queued',
  pr_url      text,
  log_excerpt text,             -- last few lines of `replicas read` for debugging
  reason      text,             -- "initial generation" | "rot at NN% failure rate"
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);
create index if not exists extractor_jobs_domain_idx
  on extractor_jobs(domain, created_at desc);
-- A domain can only have one *active* job at a time. Defining the partial
-- unique index up front prevents future Replicas spawns from racing.
create unique index if not exists extractor_jobs_one_active
  on extractor_jobs(domain)
  where status in ('queued', 'running');

drop trigger if exists trg_extractor_jobs_updated on extractor_jobs;
create trigger trg_extractor_jobs_updated
  before update on extractor_jobs
  for each row execute function set_updated_at();
