-- v0.7: Research Scoping & Source Tiering
-- Adds columns to analysis_runs for the new scoping step and tiered-source metrics.
-- Do NOT run automatically — apply manually via the Supabase SQL editor.

alter table analysis_runs
  add column if not exists scoping_sec numeric,
  add column if not exists num_candidate_regimes integer,
  add column if not exists pct_tier1_sources numeric,
  add column if not exists scope_json jsonb;
