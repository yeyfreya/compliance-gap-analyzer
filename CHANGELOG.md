# Changelog — AI Compliance Gap Analyzer

All notable changes to this project are documented here.
Each version represents an iteration, including what was analyzed, what changed, and why.

---

## [v0.7] - 2026-08-12 — Research Scoping & Source Tiering

### Summary
v0.6 fixed the pipeline's date defect and the reports got *worse* — knowing today's date let
the model compare a stale research fact against the calendar and declare a deadline missed that
had actually been deferred. The date was a symptom; source quality was the disease. v0.7
replaces free-form search planning with a structured scoping stage, makes research prefer
authoritative sources by construction, and has the report show its own assumptions and coverage.

### What Changed
- **New pipeline stage — `scope_analysis()`** (`agent.py`, `prompts.py`): a Claude call that
  runs *before* any searching and maps the regulatory territory across five fixed dimensions
  (jurisdiction, profession, data, activity, vendor). Returns structured JSON: `assumptions`
  (each with its basis and what changes if it is wrong), `candidate_regimes` (each with a
  status — likely applies / may apply / likely not applicable **with a checkable reason** —
  and one targeted search query), and `official_domains` for that scenario. Replaces
  `plan_searches()`, which invented 3–5 free-form queries with no coverage guarantee
- **Two-tier research** (`agent.py` `gather_research()`, `tools.py`): one targeted search per
  candidate regime instead of free-form queries, so coverage comes from the dimension list
  rather than luck. Tier 1 restricts the search to `official_domains`; Tier 2 (unrestricted)
  runs only where Tier 1 returned nothing. `search_web()` gains an `include_domains` parameter.
  Every source carries its tier through to the report
- **The report shows its own work** (`prompts.py`): two new sections — **Scope & Assumptions**
  at the top (who the analysis assumed you are, and what changes if that is wrong) and
  **Coverage** near the end (what was considered, what was ruled out *with reasoning*, and
  which authoritative domains were actually searched). Existing sections renumber; the length
  target moves from 150–250 to 180–280 lines so the gap analysis itself is not squeezed
- **Source-tier rules in the analysis prompt** (`prompts.py`): findings arrive tagged Tier 1 or
  Tier 2; any claim resting only on commentary must say so, and a quote attributed to an
  authority must come from that authority's own domain
- **No fallback on scoping failure** (`agent.py`): new `ScopingError`; one retry, then an honest
  abort rather than silently reverting to the search planner that failed its accuracy test
- **Observability extended** (`tracking.py`, `agent.py`, `streamlit_app.py`, `migrations/`): the
  scoping step is its own Langfuse span; two new trace scores (candidate-regime count, share of
  Tier 1 sources); `analysis_runs` gains `scoping_sec`, `num_candidate_regimes`,
  `pct_tier1_sources`, and `scope_json` — the full scoping output per run, so cross-run
  variation can be analyzed in SQL instead of by re-reading reports. SQL in `migrations/`
- **UI** (`streamlit_app.py`): step 1 is now "Scoping your regulatory territory"; research
  reports the share of official sources; the timing caption moves to "typically 2–3 minutes"

### Test Results
Three runs on one professional-services scenario, compared against a hand-verified answer key.

**Fixed:** the governing professional body was found and cited to its own domain in 3/3 runs
(v0.6 omitted it entirely in 2 of 6 runs). Vendor-policy contradictions between runs are gone —
where v0.6 asserted three mutually incompatible data-retention claims across runs, v0.7
consistently reports that the terms were not found and should be obtained directly. Every run
states which product tier it assumed and what changes if that is wrong. Reasoned exclusions
work: regimes ruled out now carry a checkable reason.

**Not fixed:** the *set* of regulations is now stable across runs, but the **ranking** is not —
which regime is called CRITICAL #1 still varies. And the tier system leaks: the search
provider's domain filter is not strict, and a scoping call occasionally lists an
official-looking commercial site as authoritative, so some commentary reaches the analysis
carrying an official-source tag. One run repeated the v0.6 "deadline has passed" error from a
leaked commentary source. Source quality remains the binding constraint. The fix is
deterministic tier verification in code rather than trusting the search provider's filter;
that is not yet implemented.

**Timing:** ~165–180s per run, up from ~110s on v0.6 — one additional Claude call plus one
search per candidate regime.

---

## [v0.6] - 2026-03-10 — Pipeline Hardening & Prompt Fixes

### Summary
Systematic fix of all remaining issues from the v0.5 backlog, prioritized by impact.
HIGH: research failure surfacing, misleading system prompt, research adequacy loop.
MEDIUM: report quality heuristics, user feedback, token reduction, source inclusion.

### What Changed
- **Research now returns structured data** (`agent.py`, `conduct_research()`): returns a dict
  (findings text, sources, successful/failed queries, result count) instead of a flat string —
  the foundation for the failure-surfacing, sources, and adequacy fixes below
- **No reports from empty research** (`agent.py`, `streamlit_app.py`): new `EmptyResearchError`;
  the pipeline aborts with a calm retry message instead of writing a fabricated report when no
  searches return results. Thin-but-nonzero research is flagged with a limitations note (#29)
- **Honest system prompt** (`prompts.py`): removed the false "you have access to web search
  tools" claim; the prompt now accurately describes that findings are supplied to Claude, and
  instructs it to flag thin findings rather than invent specifics (#9)
- **Research adequacy check** (`agent.py`, `gather_research()`): if the first research pass is
  thin (< 4 results), one broadened supplementary search round runs and merges (dedup by URL).
  Lightweight heuristic; full agentic loop deferred to v0.7 (#7)
- **Sources in the report** (`agent.py` `save_report()`, `streamlit_app.py`): reports gain a
  "Sources" section (markdown links); the UI gains a "🔗 Sources" tab (#14)
- **Feedback button** (`streamlit_app.py`): 👍/👎 "Was this report helpful?" under each report,
  stored in the existing `user_events` table — no schema migration (#31)

Deferred as planned: #30 (quality heuristics), #13 (research preprocessing), and LOW items
(#8, #23, #24, #25, #32).

### Added 2026-08-07 — currency, fine print, and delivery tooling

- **Current date reaches both Claude calls** (`prompts.py`, `agent.py`): `SEARCH_PLANNING_PROMPT`
  and `ANALYSIS_PROMPT` now receive today's date. The planner had been anchoring queries to its
  training-era year — searching "…2024" for a report generated in August 2026 — and the analysis
  had no way to tell whether a deadline had already passed. New `DATES & CURRENCY` rules instruct
  the model to check every date against today, prefer newer dates when research shows one moved,
  and stay vague rather than assert a date it cannot support. `_today()` resolves per call, so a
  long-running Streamlit process cannot get stuck on its boot date
- **Disclaimer on every report** (`prompts.py`, `agent.py`, `streamlit_app.py`): new
  `REPORT_DISCLAIMER`, defined once and attached to the saved markdown, the on-screen report, the
  download and the database copy. Also re-attached in the save-failure fallback, which previously
  produced a report with no fine print
- **Custom-run CLI** (`agent.py`): `--use-case` / `--technology` / `--industry` flags, so one-off
  analyses run without adding real inputs to a file in a public repo
- **`export_pdf.py`** (new): renders a saved report as print-ready HTML for Save-as-PDF. No new
  dependencies by design. `--client-ready` drops the internal search-queries section
- **`.gitignore`**: `reports/*.html` added so exported reports stay out of the repo;
  `test-log.csv` untracked — performance logs are kept locally

Full details: [docs/iterations/v0.6-pipeline-hardening-and-prompt-fixes.md](docs/iterations/v0.6-pipeline-hardening-and-prompt-fixes.md)

---

## [v0.5.1] - 2026-03-01 — README, Repo Cleanup & Architecture Doc

### Summary
Restructured the repo and documentation for public clarity. README rewritten as a
product-focused landing page. Technical decisions documented in a new ARCHITECTURE.md.
Removed unused test files and debug artifacts. Showcase reports renamed for readability.

### What Changed
- **README rewritten** (`README.md`): Product-first structure — value prop, target user, live demo, screenshot, report description, user-experience flow, example, roadmap. Installation and tech details moved lower
- **Architecture doc** (`docs/ARCHITECTURE.md`): New document covering system design, key technical decisions, and their reasoning — frontend-agnostic pipeline, three-layer error tracing, cross-service correlation, rate limiting design, Extended Thinking, report voice
- **Screenshot added** (`assets/screenshot.jpg`): Hero image of the live demo in README
- **Unused files removed from tracking**: `test_all.py`, `test_api.py`, `test_tavily.py` (v0.1 API smoke tests, superseded by `test_tracking.py`)
- **Test artifacts removed from tracking**: `reports/test_report.md`, `reports/test_correlation_report.md`
- **Showcase reports renamed**: `report_healthcare.md`, `report_fintech.md`, `report_regtech.md` (clean scenario-based names)
- **Dev logs moved to local-only**: `docs/dev-logs/` gitignored — iteration docs remain the public development history
- **Documentation guide updated** (`docs/DOCUMENTATION-GUIDE.md`): Section 8 rewritten for new README structure and voice guidelines

Full details: [docs/iterations/v0.5-error-handling-and-rate-limiting.md](docs/iterations/v0.5-error-handling-and-rate-limiting.md)

---

## [v0.5] - 2026-02-28 — Error Handling, Error Logging & Rate Limiting

### Summary
Production hardening: structured error logging to Supabase, try/except around
the full pipeline (no more raw tracebacks for users), retry logic for transient API
errors, and invisible per-session rate limiting to protect API budget without adding
user friction.

### What Changed — Session 1: Error Tracing, Rate Limiting, Report Restructure & Product Voice (2026-02-28)
- **Retry logic** (`agent.py`, `tools.py`): `_retry_api_call()` retries once with backoff on transient Claude errors (rate limits, timeouts, 500s). Tavily `search_web()` also retries once on failure
- **Error logging** (`tracking.py`, `supabase_schema.sql`): New `error_logs` table with error type, message, traceback, pipeline step, user inputs, session/run correlation. New `log_error()` and `mark_run_failed()` functions
- **Pipeline error handling** (`streamlit_app.py`): Full try/except around `_run_pipeline()` — logs error to Supabase, marks run as failed, shows friendly message with run_id reference. Separate try/except for `save_report()` with in-memory fallback
- **Rate limiting** (`tracking.py`, `streamlit_app.py`): Invisible per-session limit (3 analyses). Counts via Supabase query. Friendly limit message with contact link. Defaults to allowing if Supabase is down
- **Report restructure** (`prompts.py`, `agent.py`): Concise 5-section format (Gap Matrix → Regulatory Landscape → Gap Details → Next Steps → Bottom Line). Removed Agent Reasoning section. Reduced `max_tokens` 16000→8000, thinking budget 8000→4000. Target: 150–250 lines, under 2 min
- **Report voice** (`prompts.py`): Gentle advisor tone, "potential gaps" language, no assumptions about user's product, no fear-based language. Aligned with product name
- **UI polish** (`streamlit_app.py`): Timer "Usually about a minute", removed local file path from UI
- **Report naming** (`agent.py`): Date before slug, slug capped at 30 chars for scannability
- **Bug fix** (`streamlit_app.py`): Added `load_dotenv()` before API key check — local runs were failing
- **Agent rules** (`.cursor/rules/agent-behavior.mdc`): Added Report Voice & Product Identity (Rule 4), Token-Efficient Execution (Rule 5)

### What Changed — Session 2: Pre-Merge Review (2026-03-01)
- **Code cleanup:** Fixed `save_report()` default version `"v0.1"`→`"v0.5"`, removed unused `datetime` import from `streamlit_app.py`
- **Privacy:** Sanitized local file paths from `.cursor/rules/pre-commit-review.mdc` and `docs/dev-logs/v0.1_...`
- **README accuracy:** Updated stale content — "Risk Prioritization Matrix" → "Compliance Gap Matrix", "2–3 minutes" → "about a minute", old format description → new 5-section structure
- **Documentation guide** (`docs/DOCUMENTATION-GUIDE.md`, `.cursor/rules/documentation-system.mdc`): Added "product behavior changed" trigger for README updates — root cause fix for agents missing content-level staleness

Full details: [docs/iterations/v0.5-error-handling-and-rate-limiting.md](docs/iterations/v0.5-error-handling-and-rate-limiting.md)

---

## [v0.4] - 2026-02-27 — Supabase + Langfuse Tracking

### Summary
Set up comprehensive observability: Langfuse for AI agent tracing (extended thinking,
token usage, cost, per-step reasoning) and Supabase for user behavior tracking (sessions,
events, report persistence). Extended Thinking enabled on both Claude calls. Structured
reasoning prompts added so Claude explains its decision-making in every report.

### What Changed — Session 1: Observability Setup (2026-02-27)
- **Extended Thinking** (`agent.py`): Enabled on `plan_searches()` (3k budget) and `analyze_compliance()` (8k budget). Both now return dicts with thinking text, token counts
- **Langfuse instrumentation** (`agent.py`): `@observe()` decorators on all pipeline functions + `AnthropicInstrumentor` for automatic Claude API tracing
- **Structured reasoning** (`prompts.py`): Planning prompt asks for query rationale; analysis prompt adds "Agent Reasoning" section to every report
- **Supabase tracking** (`tracking.py`): New module — fail-safe session/run/event/report tracking via PostgREST
- **Schema** (`supabase_schema.sql`): 4 tables (sessions, analysis_runs, user_events, reports)
- **Streamlit updates** (`streamlit_app.py`): User event tracking, Supabase/Langfuse secrets injection, handles new dict return types
- **Dependencies** (`requirements.txt`): Added `postgrest`, `langfuse>=4.0.0b1`, `opentelemetry-instrumentation-anthropic`
- **Cursor rule** (`.cursor/rules/no-assumptions.mdc`): AI agent must confirm assumptions with user before acting

### What Changed — Session 2: Architecture Fix, Correlation, UI Polish & Report Sync (2026-02-28)
- **Parent Langfuse trace** (`streamlit_app.py`): Extracted pipeline into `@observe(name="compliance_pipeline")` wrapper — all three steps now group under one parent trace instead of creating separate fragmented traces. Tagged with `run_id`/`session_id` via OTel span attributes
- **Universal correlation key** (`agent.py`, `streamlit_app.py`, `sync_reports.py`): Supabase `run_id` embedded in local report headers, test-log.csv, Langfuse trace metadata, and synced reports — single key to navigate between all systems
- **Product identity** (`streamlit_app.py`): Removed "Claude" name-drops from pipeline step messages — the agent presents as the product
- **Time expectations** (`streamlit_app.py`): Timer subtitle now says "Usually 2–3 min · may take longer for complex or region-specific cases"
- **Report sync** (`sync_reports.py`): New CLI script pulls cloud-generated reports from Supabase to local `reports/` with UTC→local timestamp conversion. Idempotent
- **Agent rules consolidated** (`.cursor/rules/agent-behavior.mdc`): Combined no-assumptions, root-cause surfacing, and product marketing thinking into one rule. Deleted standalone `no-assumptions.mdc`
- **CSV column migration** (`agent.py`, `sync_reports.py`): `run_id` column added to test-log.csv with automatic one-time header migration for existing CSVs
- **Integration tests** (`test_tracking.py`): Expanded from basic connection test to 4-part test suite: Supabase cross-table linkage, Langfuse connection, parent trace architecture (nested spans + metadata), local report correlation (run_id in report header + CSV)
- **Known non-bug rule** (`.cursor/rules/documentation-system.mdc`): Documented Windows GBK emoji error as Cursor shell bug — agents must not strip emoji from code

### What Changed — Session 3: Branching (2026-02-28)
- **Branching guide** (`docs/BRANCHING-GUIDE.md`): main/dev workflow, PR-based merges, release tagging, optional staging app for Streamlit Cloud testing
- **Docs updated**: DOCUMENTATION-GUIDE workflow, README project structure and Development section

Full details: [docs/iterations/v0.4-supabase-langfuse-tracking.md](docs/iterations/v0.4-supabase-langfuse-tracking.md)

---

## [v0.3] - 2026-02-26 — Streamlit UI & Report Structure

### Summary
Built a Streamlit web interface for live demo — users can input their AI scenario and
receive a full compliance gap report through a polished UI. Added mandatory Risk
Prioritization Matrix as the first section of every report.

### What Changed — Session 1: UI & Report Structure
- **Streamlit app** (`streamlit_app.py`): Full web UI with sidebar scenario picker, step-by-step progress tracking, live JS elapsed timer, timing metrics cards, tabbed report/queries view, and markdown download button
- **Theme** (`.streamlit/config.toml`): Dark theme with blue primary color
- **Analysis prompt rewrite** (`prompts.py`): Risk Prioritization Matrix enforced as first section; standardized risk levels (CRITICAL/HIGH/MEDIUM/LOW); flexible structure for detailed analysis sections
- **Bug #17 closed** (`agent.py`): Windows GBK encoding error investigated — only occurs in Cursor's shell runner, not in user's own terminal. Not a code bug; no fix applied
- **New test scenario** (`agent.py`): `regtech` — the tool analyzing itself (RegTech / AI compliance SaaS)
- **Timer UX**: Live JS clock counts during analysis, stops on completion with static "Report generated in X:XX"

### What Changed — Session 2: Cloud Deployment - 2026-02-27
- **Streamlit Cloud secrets** (`streamlit_app.py`): Injects `st.secrets` as env vars before agent import; clear error message if secrets are missing
- **Pinned requirements** (`requirements.txt`): Added `>=` floor versions for all dependencies
- **Deployed to Streamlit Cloud**: Live public demo connected to GitHub repo

### Test Results
- 4 Streamlit test runs: regtech (x2), documentation tool, HR — all passed
- Analysis time: 48s–185s depending on regulatory complexity and report length
- Reports: 289–789 lines with structured prompt

Full details: [docs/iterations/v0.3-streamlit-ui.md](docs/iterations/v0.3-streamlit-ui.md)

---

## [v0.2] - 2026-02-26 — Bug Fixes, Hardening & Observability

### Summary
Fixed all critical/high bugs from v0.1 baseline. Added test scenario runner, per-step
timing, and centralized performance logging — the project's first AI observability layer.
Tested across 4 diverse regulatory scenarios (HR, Healthcare, Fintech, Education).

### What Changed — Bug Fixes (Session 1)
- **Bug #1 fixed:** `format_search_results()` in `tools.py` — function received a list but treated it as a dict, causing all research data to be silently dropped. Now iterates the list directly.
- **Bug #2 closed:** Indentation inconsistency in `run_analysis()` — already fixed in prior session.
- **Bug #15 fixed:** `max_tokens` in `analyze_compliance()` increased from 3000 to 8000 — v0.1 test run confirmed analysis was truncating mid-table.
- **Bug #3 fixed:** Added `anthropic.APIError` handling to both Claude API calls in `agent.py` — pipeline degrades gracefully instead of crashing on API failures.
- **Bug #4 fixed:** Input validation on `run_analysis()` — rejects empty/whitespace/overlength inputs with error dict before any API calls are made.
- **Bug #6 closed:** Bare `except` in `plan_searches()` — already fixed in prior session (catches specific exceptions).

### What Changed — Test & Observability (Session 2)
- **Test scenarios:** Added `TEST_SCENARIOS` dict with 4 scenarios + CLI runner (`python agent.py <scenario>`)
- **Timing:** Per-step timing (planning, research, analysis) in `run_analysis()`, displayed in console output and report header
- **Test log:** New `append_test_log()` writes to `reports/test-log.csv` after every run — centralized performance tracking across versions
- **Test results:** All 4 scenarios passed. Analysis phase is the bottleneck (75-85% of total time). Report length varies 266-790 lines by regulatory complexity.

### What Changed — Docs, README & Rename (Session 3)
- **Documentation system:** Added README update rules (Section 7) to DOCUMENTATION-GUIDE.md with trigger table and workflow integration
- **Cursor rules synced:** Fixed dev log naming format (added HHMM), added commit message suggestion step
- **Documentation map:** Created local-only `docs/DOCUMENTATION-SYSTEM-MAP.md` — visual reference for the full documentation system
- **README updated to v0.2:** Status, architecture diagram, project structure, usage (CLI scenarios), known issues, roadmap, current version
- **Repo renamed:** `compliance-gap-analyzer` → `ai-compliance-gap-analyzer`; all current-state references updated

### New Issues Found
- #16: Analysis prompt doesn't enforce consistent report structure (Medium)
- #17: Windows GBK encoding error on emoji output (Medium)

Full details: [docs/iterations/v0.2-bug-fixes-and-observability.md](docs/iterations/v0.2-bug-fixes-and-observability.md)

---

## [v0.1] - 2026-02-25 — Baseline

### Summary
First working version of the AI Compliance Gap Analyzer. Three-stage pipeline
that plans searches, executes web research via Tavily, and sends findings to
Claude for structured compliance analysis.

### Architecture
- **agent.py** — Main orchestrator with 5 functions:
  `plan_searches()` → `conduct_research()` → `analyze_compliance()` → `save_report()` → `run_analysis()`
- **tools.py** — Web search via Tavily API with result formatting
- **prompts.py** — System prompt, search planning prompt, and analysis prompt
- **test_all.py / test_api.py / test_tavily.py** — Manual integration tests

### What Works
- End-to-end pipeline: user provides (use_case, technology, industry) → gets compliance gap report
- Claude plans 3-5 search queries dynamically
- Tavily executes advanced web searches
- Claude analyzes findings and produces structured report
- Reports saved as timestamped markdown files

### Analysis (14 findings from "Improve & Debug" chat)
- 2 bugs found (format_search_results type mismatch, indentation)
- 4 missing features (error handling, input validation, retry logic, specific exceptions)
- 2 architecture observations (linear pipeline not agent, stateless Claude calls)
- 2 prompt issues (misleading system prompt, generic analysis prompt)
- 2 code quality items (no version pins, unused streamlit dependency)
- 2 output quality items (raw research text, no sources in report)

Full details: [docs/iterations/v0.1-baseline.md](docs/iterations/v0.1-baseline.md)
