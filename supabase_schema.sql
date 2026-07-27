-- Supabase Schema for AI Compliance Gap Analyzer v0.4
-- Run this in Supabase SQL Editor (Dashboard > SQL Editor > New Query)
-- Tables: sessions, analysis_runs, user_events, reports
-- AI agent observability (steps, thinking, tokens) is handled by Langfuse.

-- 1. Sessions — one row per user visit
create table sessions (
  id uuid primary key default gen_random_uuid(),
  streamlit_session_id text not null,
  app_version text not null,
  started_at timestamptz not null default now()
);

-- 2. Analysis runs — one row per pipeline execution
create table analysis_runs (
  id uuid primary key default gen_random_uuid(),
  session_id uuid references sessions(id),
  use_case text not null,
  technology text not null,
  industry text not null,
  scenario_source text not null default 'custom',
  app_version text not null,
  status text not null default 'running',
  error_message text,
  planning_sec real,
  research_sec real,
  analysis_sec real,
  total_sec real,
  num_sources integer,
  research_limited boolean,
  num_failed_queries integer,
  started_at timestamptz not null default now(),
  completed_at timestamptz
);

-- 3. User events — event log for UI interactions
create table user_events (
  id uuid primary key default gen_random_uuid(),
  session_id uuid references sessions(id) not null,
  run_id uuid references analysis_runs(id),
  event_type text not null,
  event_data jsonb,
  created_at timestamptz not null default now()
);

-- 4. Reports — full report storage (solves ephemeral cloud reports issue)
create table reports (
  id uuid primary key default gen_random_uuid(),
  run_id uuid references analysis_runs(id) not null,
  report_markdown text not null,
  search_queries jsonb not null,
  report_filename text not null,
  created_at timestamptz not null default now()
);

-- 5. Error logs — structured error tracking for debugging (v0.5)
create table error_logs (
  id uuid primary key default gen_random_uuid(),
  session_id uuid references sessions(id),
  run_id uuid references analysis_runs(id),
  error_type text not null,
  error_message text not null,
  error_traceback text,
  pipeline_step text,
  user_inputs jsonb,
  app_version text not null,
  created_at timestamptz not null default now()
);

-- Disable Row Level Security (portfolio project, no user auth).
-- Add RLS policies if this goes to production with user accounts.
alter table sessions disable row level security;
alter table analysis_runs disable row level security;
alter table user_events disable row level security;
alter table reports disable row level security;
alter table error_logs disable row level security;

-- ── Migration (v0.6) — run this if analysis_runs already exists ───────────────
-- Adds research-quality columns for observability filtering (num_sources,
-- research_limited, num_failed_queries). Safe to run once on an existing table;
-- "if not exists" makes it a no-op if already applied.
alter table analysis_runs add column if not exists num_sources integer;
alter table analysis_runs add column if not exists research_limited boolean;
alter table analysis_runs add column if not exists num_failed_queries integer;

-- Indexes for common queries
create index idx_analysis_runs_session on analysis_runs(session_id);
create index idx_analysis_runs_started on analysis_runs(started_at);
create index idx_user_events_session on user_events(session_id);
create index idx_user_events_type on user_events(event_type);
create index idx_reports_run on reports(run_id);
create index idx_error_logs_session on error_logs(session_id);
create index idx_error_logs_created on error_logs(created_at);
