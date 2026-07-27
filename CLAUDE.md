# CLAUDE.md — AI Compliance Gap Analyzer

This file tells Claude Code how to work on this project. Read it fully before doing anything.

---

## ⚠️ Agent Behavior Rules — Read Before Anything Else

These rules govern how you work on this project. They are not suggestions. Violating them — even with good intentions — causes harm to the work.

### Rule 1 — No Assumptions: Confirm Before Acting

When the user describes what they want, do NOT silently interpret, downgrade, or simplify their intent based on what seems "more likely" or "standard."

- **If the request is ambiguous or could be interpreted multiple ways, ask before proceeding.** Do not pick the interpretation that seems most common or easiest.
- **If you are about to scope down, simplify, or reframe what the user asked for, STOP and confirm first.** Example: if they say "log Claude's reasoning process" and you think they might just mean input/output metadata — ask, don't assume.
- **Never rationalize an assumption in your internal thinking and then act on it.** The user cannot see your thinking. If you're uncertain, surface it as a question.

**BAD:** "I'm realizing the user probably just wants X" → proceeds with X
**GOOD:** "You mentioned X — did you mean [option A] or [option B]?" → waits for answer

---

### Rule 2 — Present Before Acting. Always.

When asked to check, fix, improve, clean up, restructure, or implement anything:

1. **Present your assessment first** — what you found, what you'd change, and why.
2. **Wait for explicit confirmation** before making any edits.
3. Act only after the user confirms.

**The only exception:** Single mechanical operations with literally nothing to decide — "rename this variable to X", "add this exact line here." The complete output can be described in one sentence with zero choices remaining.

**Anti-rationalization check:** If you find yourself reasoning about whether the current instruction qualifies as the exception — building a case for why it's "clear enough" or "unambiguous" — stop. That reasoning process itself is the signal that it doesn't qualify. Present first.

**Common failure mode:** The user gives a clear directional instruction ("do option C", "restructure this file"). The agent interprets direction as complete specification and skips presenting. Direction is not specification. If implementation choices remain — structure, ordering, wording, what to include — present first.

**BAD:** Agent finds 4 issues → fixes all 4 in the same response
**GOOD:** Agent finds 4 issues → presents them → asks "which of these should I change?"
**EXCEPTION:** "Add this screenshot to the README" → zero choices, just do it

---

### Rule 3 — Surface Architectural Root Causes

When investigating a problem or implementing a feature, always look for the deeper architectural issue before patching the symptom.

- **If you discover a structural or architectural gap while working on a task, STOP and surface it before acting on the symptom.** The root cause may change the scope or approach entirely.
- Frame it clearly: "I found an architectural gap that's causing this — fixing it properly would involve X. Want me to address the root cause instead of the symptom?"
- **Never silently work around an architectural issue** with a band-aid fix when you can see the root cause.
- Prioritize the higher-level fix when it solves the problem more completely and prevents future issues.

**BAD:** User asks "tag each function with metadata" → agent tags each function individually, ignoring that the functions create separate Langfuse traces instead of one grouped parent trace
**GOOD:** "I noticed the functions create separate Langfuse traces instead of being grouped under one parent trace — that's the root cause of your correlation problem. Want me to fix the architecture (add a parent trace) instead of patching each function?"

---

### Rule 4 — Product Marketing Thinking for User-Facing Content

When writing, editing, or reviewing any user-facing content (UI text, step messages, status labels, error messages, copy, tooltips):

- **The product is the agent, not the underlying model.** Never expose implementation details (e.g., "Claude is writing the report") that make users think they could replicate the value with a raw API call.
- **Frame capabilities as product features**, not descriptions of what an open-source tool is doing under the hood.
- **Every user-facing string is a branding opportunity.** Ask: "Does this make the product feel valuable and distinct, or does it feel like a thin wrapper?"
- **Set honest expectations** without underselling. If something takes variable time, say so without being vague or alarming.

**BAD:** "Claude is analyzing your data…"
**GOOD:** "The agent is cross-referencing findings and writing your report…"

**BAD:** "Searching Tavily for results…"
**GOOD:** "Searching the web for regulatory data…"

---

### Rule 5 — Don't Run Long Commands

Do NOT run test suites, Streamlit launches, or long-running commands in the Claude Code shell:
- `python test_tracking.py` — prepare the command, let the user run it
- `streamlit run streamlit_app.py` — same
- `python agent.py <scenario>` — same

Focus tokens on reading files, writing code, architectural analysis, and documentation.
When a task is "run this and check the result", hand it off with a clear command and what to look for.

---

## What This Project Is

An AI-powered compliance gap analysis tool for early-stage AI startups. Users describe
their AI use case, technology, and industry — the agent plans searches, researches
current regulations via Tavily, cross-references them against LLM/technology compliance
obligations, and delivers a structured gap report.

**Current version:** v0.6
**Live demo:** https://ai-compliance-gap-analyzer.streamlit.app/
**Branch:** `dev` for active work, `main` for stable/deployed, PRs for every merge.

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| AI orchestration | Claude Sonnet 4.5 (`claude-sonnet-4-5-20250929`) with Extended Thinking |
| Web research | Tavily API |
| AI observability | Langfuse (traces, thinking, token/cost) |
| Database | Supabase via PostgREST (sessions, runs, events, reports, error_logs) |
| Frontend | Streamlit (temporary — core pipeline is frontend-agnostic) |
| Language | Python 3.14 |

---

## Key Files

| File | Purpose |
|------|---------|
| `agent.py` | Core pipeline: `plan_searches()` → `conduct_research()` → `analyze_compliance()` → `save_report()` → `run_analysis()`. Also `append_test_log()` and `TEST_SCENARIOS`. |
| `streamlit_app.py` | Streamlit UI. Handles secrets injection, session tracking, rate limiting, error display. Defines `VERSION`. |
| `tracking.py` | Supabase tracking — fail-safe, silently disabled if env vars missing. |
| `tools.py` | Tavily web search + result formatting. |
| `prompts.py` | `SYSTEM_PROMPT`, `SEARCH_PLANNING_PROMPT`, `ANALYSIS_PROMPT`. |
| `sync_reports.py` | CLI utility to pull cloud reports from Supabase to local `reports/`. |
| `test_tracking.py` | Integration test suite (Supabase, Langfuse, run_id correlation). |
| `requirements.txt` | Python dependencies with floor versions. |

**Version is defined in two places — always update both together:**
1. `version` default parameter in `run_analysis()` in `agent.py`
2. `VERSION` constant in `streamlit_app.py`

---

## Before Starting Any Work

**Each session has one PRIMARY focus — but stay flexible, never rigid.** At the start, if the
primary focus isn't already clear, do any trivial startup task (e.g. copying the prior
transcript), then **ASK the user which focus to center on** — from the menu in the latest dev
log's "START OF EVERY SESSION" section (and reflected in auto-loaded memory) — and keep the
session centered there. The user thinks associatively: tangential ideas about other topics
WILL surface mid-session, and that is welcome. When one does, **PARK it** — add it to the focus
menu (as a future session) or log it in the right doc (ROADMAP, competitor analysis, etc.) so
it isn't lost — then return to the primary focus. The goal is to protect BOTH progress and
ideas. Never let this rule block the user's flow.

Read these files before touching anything. Grouped by what they tell you:

### Project identity & current state
- `README.md` — product value proposition, target user, report structure, tone, live demo
- `CHANGELOG.md` — version history and what changed in each version
- `docs/iterations/` — read the **latest** file (highest version number) for current known issues, test results, and remaining work

### Strategy & architecture
- `docs/PROJECT-SCHEMA.md` — project vision, phased strategy, and key architectural decisions with sourced reasoning *(local only, not in git)*
- `docs/ROADMAP.md` — cross-version plan by pillar: pipeline reliability, accuracy, trustworthiness, product direction — with status per item *(local only, not in git)*
- `docs/ARCHITECTURE.md` — public: system design, pipeline flow, key technical decisions

### Documentation conventions
- `docs/DOCUMENTATION-GUIDE.md` — full doc structure, naming conventions, workflow, when to update each file

### Core code
- `prompts.py` — the system prompt and analysis prompt that define report structure and voice
- `agent.py` — core pipeline: `plan_searches()` → `conduct_research()` → `analyze_compliance()` → `save_report()` → `run_analysis()`
- `streamlit_app.py` — UI, session/run tracking, rate limiting, error handling, `VERSION` constant
- `tracking.py` — Supabase tracking functions and rate limiting logic
- `tools.py` — Tavily search wrapper

### Config
- `requirements.txt` — current dependencies and version floors

---

## After Completing Work

- Update `docs/iterations/v<VERSION>-*.md` with changes, test results, new findings
- Write a dev log summary in `docs/dev-logs/` — naming: `v<VERSION>_<YYYY-MM-DD>_<HHMM>_<short-topic>.md`
- Update `CHANGELOG.md` if a new version was created
- Update `README.md` if version, known limitations, roadmap, project structure, or **product behavior** changed (timing, report format, terminology, output structure) — scan the full README for stale prose, not just version numbers
- Update `docs/PROJECT-SCHEMA.md` if any strategic decisions were made (new direction, target user, architecture)
- Update `docs/ROADMAP.md` if product direction thinking evolved, an item's status changed, or new items were identified
- **End every dev log with an updated "next focuses" menu** — the remaining dedicated sessions (each its own future session), plus any ideas parked mid-session, so the handoff is a self-contained snapshot. Remove focuses that are now done.
- **Refresh memory to match** — update the auto-loaded focus menu in memory (`project-business-pivot-and-repo-split` and `MEMORY.md`) so the next session surfaces the current state without needing to open a specific dev log. Memory is the authoritative startup source; dev logs are per-session snapshots.
- Suggest a commit message: `v<VERSION>: <what changed> + docs`
- Remind the user to export the chat transcript from their IDE into `docs/dev-logs/transcripts/`

---

## Report Voice Rules

The report output is the product. Its voice is strictly defined.

- **Gentle advisor, not auditor.** Reader is a busy startup founder. Tone is warm, supportive, informative.
- **Never assume what the user has or hasn't done.** Say "worth confirming" not "you don't have." Say "if not already addressed" not "you are violating."
- **"Potential gaps" language** — consistent with the product name. Findings are framed as potential gaps between industry compliance requirements and LLM/technology obligations.
- **No fear-based language.** No "cease immediately", "illegal", "existential risk", "you face prosecution." Instead: "this carries significant regulatory weight", "regulators are actively focused on this area."
- **Scannable and concise.** Reports target 150–250 lines. Every sentence earns its place.

**BAD:** "No FDA clearance for diagnostic software" → assumes violation
**GOOD:** "FDA clearance for diagnostic software" → frames as area to check

This voice is enforced in `prompts.py` (`ANALYSIS_PROMPT`) and must be preserved when editing prompts.

---

## Pre-Commit Checklist

Run this before helping the user commit or push. Report findings as a table with Pass / Warning / Fail per check.

**Security**
- [ ] No API keys, tokens, or secrets in any staged file
- [ ] No `.env` files staged
- [ ] No credentials, passwords, or connection strings

**Privacy**
- [ ] No personal email addresses in file contents
- [ ] No local file paths (`C:\Users\<username>\...`, `D:\<projects>\...`)
- [ ] No private data that shouldn't be public

**Files**
- [ ] `.gitignore` protects: `.env`, `.cursor/`, `docs/dev-logs/`, `docs/dev-logs/transcripts/`, `docs/PROJECT-SCHEMA.md`, `docs/ROADMAP.md`
- [ ] No duplicate or unnecessary files staged
- [ ] No files that belong in `.gitignore` but are being committed

**Code quality** (if code files are staged)
- [ ] No bare `except:` clauses
- [ ] No hardcoded secrets or credentials
- [ ] Consistent formatting and indentation

**Documentation** (if a versioned commit)
- [ ] `CHANGELOG.md` updated
- [ ] Iteration doc updated
- [ ] Dev log written for the session

---

## Known Non-Bugs — Do NOT Fix

**Windows emoji / UnicodeEncodeError (GBK codec):** Claude Code's shell on Windows may fail
to render emoji with `UnicodeEncodeError: 'gbk' codec can't encode character`. This is a
shell runner limitation on Windows, NOT a code bug. The user's own terminal (PowerShell, cmd)
handles emoji fine. **Do NOT strip emoji from print statements.** Leave them as-is.

---

## Git Workflow

- **Active work:** `dev` branch
- **Stable/deployed:** `main` branch (Streamlit Cloud deploys from here)
- **Merges:** Always via Pull Request, even as a solo developer — creates documented checkpoints
- **Tags:** Tag releases on main after merging (e.g., `git tag v0.5`)

**Commit message format:**
```
v<VERSION>: <what changed> + docs
```

Examples:
- `v0.5: Error handling, rate limiting, report redesign + docs`
- `v0.5.1: Restructure repo for public presentation + ARCHITECTURE.md + docs`

Never skip hooks (`--no-verify`). Never force-push to main.

---

## Documentation Structure (quick reference)

```
docs/
├── DOCUMENTATION-GUIDE.md      # Full conventions — read first
├── ARCHITECTURE.md             # Public: system design and decisions
├── BRANCHING-GUIDE.md          # Git workflow
├── PROJECT-SCHEMA.md           # LOCAL ONLY: vision, strategy, sourced quotes
├── ROADMAP.md                  # LOCAL ONLY: cross-version plan by pillar
├── iterations/                 # One file per version — public development story
│   └── v<VERSION>-<description>.md
└── dev-logs/                   # LOCAL ONLY — chat session summaries
    ├── v<VERSION>_<YYYY-MM-DD>_<HHMM>_<topic>.md
    └── transcripts/            # LOCAL ONLY — full exported chat logs
```

```
reports/
├── report_healthcare.md        # Showcase report (tracked in git)
├── report_fintech.md           # Showcase report (tracked in git)
├── report_regtech.md           # Showcase report (tracked in git)
├── report_v<VERSION>_*.md      # Auto-generated (gitignored)
└── test-log.csv                # Performance log — always tracked, append-only
```

---

## Universal Correlation Key

Every analysis run generates a `run_id` (UUID) embedded in:
- Local report header
- Supabase `analysis_runs` and `reports` tables
- Langfuse trace metadata
- `reports/test-log.csv`

If a user reports a problem, the `run_id` from their error message traces to the full
execution across all three systems. Preserve this pattern in any pipeline changes.

---

## Supabase Database Tables

| Table | Purpose |
|-------|---------|
| `sessions` | One per browser session |
| `analysis_runs` | One per analysis — inputs, timing, status, `run_id` |
| `user_events` | Granular interaction tracking |
| `reports` | Full report markdown, linked to `run_id` |
| `error_logs` | Error type, traceback, pipeline step, user inputs, session/run correlation |

`tracking.py` is fail-safe — Supabase errors are caught and logged but never crash the app.
If `SUPABASE_URL`/`SUPABASE_KEY` are missing, tracking is silently disabled.
