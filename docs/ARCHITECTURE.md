# Architecture & Technical Decisions

How the AI Compliance Gap Analyzer is built, and the reasoning behind key design choices.

---

## System Overview

```
┌──────────────┐     ┌──────────────────────────────────────────────┐
│   Frontend   │     │              Core Pipeline                   │
│  (Streamlit) │────▶│                                              │
│              │     │  run_analysis(use_case, technology, industry) │
│  Temporary   │     │       │                                      │
│  — any UI    │     │       ├─ scope_analysis()  → Claude (thinking)│
│  can replace │     │       ├─ gather_research() → Tavily (tiered) │
│  this layer  │     │       └─ analyze_compliance() → Claude (report)│
└──────────────┘     │                                              │
                     │  Returns a predictable result dict.          │
                     │  Never crashes. Never throws raw API errors. │
                     └──────────┬───────────────────────────────────┘
                                │
               ┌────────────────┼────────────────┐
               ▼                ▼                ▼
        ┌─────────────┐  ┌───────────┐   ┌─────────────┐
        │  Supabase    │  │  Langfuse  │   │  Local Files │
        │  (Postgres)  │  │  (AI Obs)  │   │  (Reports)   │
        │              │  │            │   │              │
        │  Sessions    │  │  Traces    │   │  Markdown    │
        │  Runs        │  │  Thinking  │   │  reports     │
        │  Events      │  │  Tokens    │   │  test-log.csv│
        │  Reports     │  │  Cost      │   │              │
        │  Error logs  │  │            │   │              │
        └──────┬───────┘  └─────┬──────┘   └──────┬──────┘
               │                │                 │
               └────────────────┼─────────────────┘
                                │
                          run_id (UUID)
                    Universal correlation key
```

A single `run_id` connects every piece of data across all three systems — you can start from a local report file, look up the same run in Supabase, and trace the full AI reasoning in Langfuse.

---

## Key Design Decisions

### 1. Frontend-agnostic core pipeline

The current Streamlit UI is a temporary frontend for launching a live demo quickly. The core pipeline (`run_analysis()`) is a self-contained function that any frontend can call — Streamlit, Flask, FastAPI, or a plugin for an AI agent platform.

This decision shaped where error handling, input validation, retry logic, and timing live: **all in the core, not in the UI layer.** The pipeline always returns a predictable dict — it never crashes, never throws raw API errors at the caller. Any future frontend just calls it and gets a clean result.

### 2. Three-layer error tracing

Not all errors are the same. The system distinguishes three layers:

| Layer | What goes wrong | How it's handled |
|-------|----------------|-----------------|
| **Code crashes** | Python exceptions, API failures | try/except → Supabase `error_logs` with full context (traceback, pipeline step, user inputs, run_id). Retry once with backoff for transient API errors |
| **Bad output** | Pipeline succeeds but report quality is poor | Future: output quality heuristics + user feedback mechanism |
| **Platform issues** | Streamlit Cloud downtime | UptimeRobot monitoring |

Error logging goes to Supabase (not Sentry or file-based logging) because the infrastructure already exists with session/run correlation keys — every error is automatically linked to the user session, run inputs, and pipeline step that caused it.

### 3. Cross-service correlation via `run_id`

Every analysis run generates a UUID (`run_id`) that's embedded in:
- The local markdown report header
- The Supabase `analysis_runs` and `reports` tables
- The Langfuse trace metadata
- The local `test-log.csv`

This means you can navigate from any system to any other system using a single key. If a user reports a problem, the `run_id` from their error message traces back to the full pipeline execution across all three data stores.

### 3b. Scoping before searching, and tiered sources (v0.7)

The original pipeline asked Claude to invent 3–5 search queries, then analyzed whatever those
queries happened to return. Two problems followed from that, and both showed up in testing:
nothing guaranteed that an important regulation was researched at all, and the analysis was only
ever as good as whatever ranked highly in a general web search — including blogs quoting
standards bodies inaccurately.

v0.7 splits the work in two:

**Scoping runs before any search.** A Claude call maps the territory across five fixed
dimensions — jurisdiction, profession, data, activity, vendor. The questions generalise to any
industry; the answers do not. It returns structured data rather than prose: the assumptions it
is making (each with what changes if it is wrong), the candidate regulations with a status per
regime, and the authoritative domains for that specific scenario.

**Research is then targeted and tiered.** One search per candidate regulation, so coverage comes
from the dimension list rather than from luck. Tier 1 restricts the search to the authoritative
domains scoping identified; Tier 2 runs unrestricted only where Tier 1 came back empty. Every
source carries its tier into the analysis, and claims resting only on Tier 2 must say so.

The key insight is that "prefer official sources" cannot be a fixed setting — the right domains
depend entirely on the scenario. Scoping is what produces them, which is why these are one
change rather than two.

**Known limitation:** the tier label is currently only as reliable as the search provider's
domain filter and the model's domain list, so some commentary can still arrive tagged as
official. Verifying tier membership in code, rather than trusting either, is the next step.

### 4. Extended Thinking for reasoning transparency

All Claude calls (scoping and compliance analysis) use Extended Thinking — Claude's internal reasoning process is captured and logged to Langfuse, not just the final output. This serves two purposes:
- **Debugging:** When a report has quality issues, we can inspect what Claude was thinking, not just what it produced
- **Observability:** Token usage for thinking vs. output is tracked separately, informing cost optimization

### 5. Zero-friction rate limiting

The live demo has invisible per-session rate limiting to protect the API budget. The design constraint: **no sign-up, no access codes, no onboarding friction.** Users should be able to go directly to the core function and see the value immediately.

Rate limiting only surfaces when the limit is hit, with a friendly message. It defaults to *allowing* requests if Supabase is down — availability over protection, because the demo's purpose is to show the product works.

### 6. Report voice as a product decision

The report output is the product. Its voice is intentionally designed:
- **Gentle advisor, not auditor.** The reader is a busy startup founder.
- **Never assumes what the user has or hasn't done.** Uses "worth confirming" and "if not already addressed," not "you don't have" or "you are violating."
- **"Potential gaps" language** — consistent with the product name (Gap Analyzer). Findings are framed as potential gaps between industry compliance requirements and AI/technology obligations.
- **Scannable and concise.** Reports target 180–280 lines. Every sentence earns its place.
- **The report shows its own work.** Since v0.7 it opens with the assumptions the analysis rests on and closes with what was considered, what was ruled out *and why*, and which authoritative domains were searched. An exclusion is only worth anything if a reader can check the reasoning.

This voice is enforced in the analysis prompt and codified in the project's agent behavior rules, so it stays consistent across versions.

### 7. AI observability from day one

Performance tracking was introduced in v0.2 — before the product was even shipped publicly. Every run logs:
- Per-step timing (planning, research, analysis)
- Total pipeline duration
- Query count
- Version tag

This data lives in `test-log.csv` (local) and Supabase (cloud), with Langfuse providing deeper AI-specific metrics (token usage, cost per trace, thinking token breakdown). The intent is to catch regressions early and make data-driven decisions about prompt optimization and cost management.

---

## Tech Stack

| Component | Technology | Why |
|-----------|-----------|-----|
| **AI orchestration** | Claude Sonnet 4.5 (Anthropic) with Extended Thinking | Reasoning transparency + high-quality analysis |
| **Web research** | Tavily API | Purpose-built for AI agent web search |
| **AI observability** | Langfuse | Traces, thinking capture, token/cost tracking |
| **Database** | Supabase (Postgres) | Free tier, PostgREST API, session/run/error correlation |
| **Frontend** | Streamlit | Fast to build, sufficient for demo — temporary |
| **Language** | Python 3.14 | Ecosystem fit for AI/ML tooling |

---

## Database Schema

Four core tables plus error logging:

- **`sessions`** — One per browser session. Tracks app version, page loads
- **`analysis_runs`** — One per analysis. Inputs, timing, status, version, `run_id`
- **`user_events`** — Granular interaction tracking (scenario selected, analysis started, report downloaded)
- **`reports`** — Full report markdown, linked to `run_id`
- **`error_logs`** — Error type, traceback, pipeline step, user inputs, session/run correlation

RLS is disabled (acceptable for a portfolio project; would need row-level security for production multi-tenant use).
