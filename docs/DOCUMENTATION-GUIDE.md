# Documentation Guide — AI Compliance Gap Analyzer

This file defines how all documentation is structured, named, and maintained in this project.
Any AI agent working on this project should follow these conventions exactly.

---

## Project Structure

```
ai-compliance-gap-analyzer/
├── agent.py                  # Main orchestrator (pipeline + test scenarios + timing + Langfuse)
├── streamlit_app.py         # Streamlit web UI (user event tracking)
├── tracking.py              # Supabase tracking (sessions, runs, events, reports)
├── sync_reports.py          # Pull cloud reports from Supabase to local reports/
├── test_tracking.py         # Integration tests (Supabase, Langfuse, run_id)
├── tools.py                 # Tavily web search and result formatting
├── prompts.py               # Prompts sent to Claude
├── supabase_schema.sql      # Database schema (run in Supabase SQL Editor)
├── requirements.txt         # Python dependencies
├── CHANGELOG.md             # Version history (summary per version)
├── .gitignore               # Protects .env, .cursor/, transcripts, dev-logs, etc.
├── .streamlit/config.toml   # Streamlit theme (dark mode)
│
├── assets/                  # Static assets (screenshot, etc.)
│   └── screenshot.jpg       # README hero image
│
├── .cursor/rules/           # Cursor rules (committed to git)
│   ├── documentation-system.mdc   # Auto-read docs before working
│   ├── agent-behavior.mdc         # No assumptions, root-cause surfacing, product identity, report voice, token efficiency
│   └── pre-commit-review.mdc      # Pre-commit checklist for agents
│
├── reports/                  # Generated compliance analysis reports
│   ├── report_<scenario>.md  # Showcase reports (tracked in git: healthcare, fintech, regtech)
│   ├── report_v<VERSION>_<YYYYMMDD_HHMM>_<slug>.md  # Auto-generated (gitignored)
│   └── test-log.csv          # Centralized performance log (AI observability)
│
└── docs/
    ├── DOCUMENTATION-GUIDE.md    # THIS FILE — how to document everything
    ├── ARCHITECTURE.md           # Public — system design and technical decisions
    ├── BRANCHING-GUIDE.md        # Git branching workflow (main/dev, PRs, tags)
    ├── PROJECT-SCHEMA.md         # LOCAL ONLY — project vision, strategy, sourced quotes
    │
    ├── iterations/               # One file per version — the full story
    │   └── v<VERSION>-<short-description>.md
    │
    └── dev-logs/                 # LOCAL ONLY — chat session summaries
        ├── v<VERSION>_<YYYY-MM-DD>_<HHMM>_<short-topic>.md
        │
        └── transcripts/         # LOCAL ONLY — not tracked in git
            └── export_v<VERSION>_<YYYY-MM-DD>_<HHMM>_<short-topic>.md
```

---

## 1. Version Iteration Docs (`docs/iterations/`)

**One file per version.** Each file tells the complete story of that version.

### Naming
`v<MAJOR>.<MINOR>-<short-description>.md`

Examples: `v0.1-baseline.md`, `v0.2-bug-fixes-and-observability.md`, `v0.3-prompt-improvements.md`

### Sections (in order)

```markdown
# v0.X — Short Description

## Project Snapshot
- Files table (file, purpose, line count)
- Architecture flow diagram

## Changes Made During This Version
- What code was added/modified and why

## Code Analysis
- Strengths
- Bugs found (with file, line, description, impact)
- Missing features
- Architecture observations
- Prompt quality issues
- Code quality items

## Test Results
- What was tested (use case, parameters)
- What worked
- What failed / issues observed
- Link to the generated report file

## Remaining Issues for v0.X+1
- Consolidated table: issue #, description, category, priority, source
- Source = "Code analysis" or "Test run"

## Version Log
- Timeline of key events during this version
```

### Rules
- Do NOT split into multiple files per version (no separate test-notes or baseline files)
- Update the file as you work through the version — it grows over time
- The "Remaining Issues" section becomes the roadmap for the next version
- **Title must stay accurate across sessions.** If a version spans multiple chat sessions that expand the scope beyond the original title, update the `# v0.X — Short Description` heading (and the filename if needed) to reflect the full scope. Example: `v0.2-bug-fixes.md` became `v0.2-bug-fixes-and-observability.md` after a second session added timing and test logging. Also update any references in `CHANGELOG.md` and dev logs.

---

## 2. CHANGELOG.md (Root)

**Short summary per version.** Points to the detailed iteration doc.

### Format

```markdown
## [v0.X] - YYYY-MM-DD — Short Title

### Summary
1-3 sentences describing what this version is about.

### Architecture
Key files and their roles.

### What Works / What Changed
Bullet points.

### Analysis
Summary counts (e.g., "14 findings: 2 bugs, 4 missing features...")

Full details: [docs/iterations/v0.X-description.md](docs/iterations/v0.X-description.md)
```

---

## 3. Reports (`reports/`)

**Generated output from running agent.py.** These are tracked in git.

### Naming
`report_v<VERSION>_<YYYYMMDD_HHMM>_<slug>.md`

Date comes right after version for scannability. Slug is capped at 30 characters.

Example: `report_v0.5_20260228_2133_ai-diagnostic-assistant.md`

### How they're created
- `save_report()` in `agent.py` generates these automatically
- The `version` parameter is passed through `run_analysis()`
- When bumping versions, update the default version string in code

### Showcase Reports

2–3 curated reports are tracked in git with clean names: `report_healthcare.md`, `report_fintech.md`, `report_regtech.md`. These are the public-facing examples visitors see in the repo.

When a new version significantly improves report quality, replace the showcase reports with better examples and keep the clean filenames.

### Rules
- Never delete old reports locally — they document what each code version produced
- **Most reports are gitignored** (`reports/report_*.md` in `.gitignore`). Showcase reports are un-ignored with `!` lines
- `test-log.csv` is **gitignored** — performance logs are kept locally. It is still append-only and never deleted

---

## 4. AI Observability (`reports/test-log.csv`)

**Centralized performance tracking across all runs and versions.**

This is the project's lightweight AI observability layer — tracking how the agent performs
over time so we can monitor latency, spot regressions, and make data-driven product decisions.

### What Gets Logged

Every successful `run_analysis()` call appends one row to `reports/test-log.csv` with:

| Column | Description |
|---|---|
| `timestamp` | When the run completed |
| `version` | Code version (e.g., `v0.2`) |
| `use_case` | Input: what the AI system does |
| `technology` | Input: technology being used |
| `industry` | Input: industry context |
| `num_queries` | How many search queries Claude planned |
| `planning_sec` | Time for Claude to plan searches |
| `research_sec` | Time for Tavily to execute all searches |
| `analysis_sec` | Time for Claude to write the analysis |
| `total_sec` | End-to-end pipeline time |
| `report_file` | Filename of the generated report |

### How It Works

- `run_analysis()` in `agent.py` wraps each pipeline step with `time.time()` calls
- Timing is included in the result dict under `result['timing']`
- `save_report()` writes timing into the report header
- `append_test_log()` appends a row to the CSV after every run

### Rules
- The CSV is append-only — never delete rows (they're your historical record)
- The CSV is tracked in git alongside reports
- When bumping versions, timing data naturally segments by the `version` column

### Future Growth

Since v0.4–v0.5, several of these have been implemented:
- ~~**Dedicated tooling**~~ — Langfuse (v0.4) for AI traces, Supabase (v0.4) for user data
- ~~**Error tracking**~~ — Supabase `error_logs` table (v0.5) with full context
- **Cost tracking** — monitor via Langfuse dashboard (token usage, cost per trace)
- **Output quality metrics** — report length, number of gaps found, number of recommendations (future)

---

## 5. Dev Logs (`docs/dev-logs/`) — LOCAL ONLY

**One summary per chat session.** Documents questions asked, answers given, and decisions made.

> **Not tracked in git.** Dev logs are kept locally for personal reference. The iteration docs (`docs/iterations/`) are the public-facing development story.

### Naming
`v<VERSION>_<YYYY-MM-DD>_<HHMM>_<short-topic>.md`

`HHMM` is the approximate session start time (24-hour format) to distinguish multiple sessions on the same day.

Example: `v0.1_2026-02-25_1711_improve-and-debug.md`

### Sections

```markdown
# Dev Log: Short Topic Title

**Version:** v0.X
**Date:** YYYY-MM-DD

## What Happened in This Session

### Task 1: Title
**Question:** What the user asked
**Answer/Solution:** What was done
**Decision:** What was decided and why
**Files modified:** List of files changed and where what changed

(repeat for each task)

## Key Decisions Made
- Numbered list of decisions

## Related Files
- Links to iteration docs, reports, transcripts
```

### Rules
- The agent writes the summary at the end of each session
- Keep it concise — capture the "what and why", not every word
- Link to related iteration docs and reports

---

## 6. Chat Transcripts (`docs/dev-logs/transcripts/`)

**Full exported chat logs — local only, not published to GitHub.**
The user exports these directly from Cursor. Remind user to do so.

### Naming
`export_v<VERSION>_<YYYY-MM-DD>_<HHMM>_<short-topic>.md`

Must match the corresponding dev log summary filename with `export_` prepended.

### Rules
- The user exports these from Cursor (not the agent)
- These are the raw record — no editing needed
- The summary file is what you read first; the transcript is for when you need exact wording
- **Not tracked in git** — listed in `.gitignore` to keep personal info (emails, local paths) private
- Kept locally for reference only

---

## 7. Project Schema (`docs/PROJECT-SCHEMA.md`)

**High-level overview of the project vision, strategy, and phased plan — local only, not tracked in git.**

This file summarizes the "big picture" by pulling sourced quotes directly from chat transcripts. It answers: what is this project, who is it for, what's the phased strategy, and what architectural decisions were made and why.

### What It Contains

- What the project is (industry, target users)
- The phased strategy (demo → temporary Streamlit → independent product or plugin)
- Key architectural decisions with sourced quotes
- Version history summary
- What's next (planned features)
- Source transcript table (which transcript said what)

### Rules
- **Local only** — listed in `.gitignore`. Contains sourced quotes from transcripts which may reference personal info.
- **Updated when the project vision, strategy, or direction changes** — not every session, only when the user makes a strategic decision (new product direction, new target user, new phase started, key architectural decision).
- **Every claim must have a source** — a direct quote and the transcript filename. Do not infer or assume; only document what the user actually said.
- **The agent should proactively update this file** when it detects a strategic decision in conversation (e.g., "I want to pivot to...", "my plan is to...", "I'm targeting...").

---

## 8. README.md (Root)

**The public-facing landing page for the product.** Written for visitors and potential users, not developers. Must stay accurate as the project evolves.

### README Structure (top to bottom)

The README is structured product-first, developer-second:

1. **Product name + value proposition** — one-line pitch
2. **Who it's for + what it does** — short paragraph
3. **Live demo link** — prominent, no-friction call to action
4. **Screenshot** — hero image of the UI/report (when available)
5. **What You Get** — describes the report output (sections, tone, value)
6. **How It Works** — user-experience flow (not code/implementation flow)
7. **Example** — sample input and what the report covers
8. **What's Coming Next** — product-facing roadmap (features users care about)
9. **Run It Locally** — installation + web UI + CLI usage (developer section)
10. **Built With** — one-line tech credits
11. **Current Status** — version, known limitations (user-facing framing)
12. **Contributing** — links to docs and branching guide
13. **Author** — name, links, license

### Voice & Framing Rules

- **Product voice, not technical spec.** The README should feel like the same product that writes the reports — warm, clear, empowering.
- **Speak to founders, not "organizations."** The target user is an early-stage AI startup founder.
- **Don't expose implementation internals.** No function names, no "Claude generates queries", no code-level flow diagrams. Show the user experience, not the architecture.
- **Known limitations, not known issues.** Frame current gaps as user-facing limitations, not internal bug tracker items. No "Supabase RLS disabled" or "silently swallowed errors."
- **Roadmap = product features, not dev checkboxes.** Show what's coming for users, not what was fixed internally.

### When to Update README.md

Update the README whenever any of these change:

| Trigger | What to Update in README |
|---|---|
| **New version started** | Current Status section (version, known limitations) |
| **Bug fixed or feature added** | Known limitations (remove fixed items), What's Coming Next |
| **Architecture changed** | Built With if applicable |
| **New known limitations found** | Current Status section |
| **Repo renamed or clone URL changed** | Installation section (git clone URL) |
| **Product behavior changed** | What You Get, Example, any prose describing how the tool works (timing, report format, terminology) |
| **Screenshot updated** | Replace screenshot image |

### Rules
- Keep the README concise — it's a product landing page, not deep documentation
- Known limitations should reflect the **current** version only (not historical); link to the iteration doc for the full list
- The version in Current Status must match the version in `agent.py`
- **Content accuracy matters:** When product behavior changes (report format, timing, terminology, output structure), scan the full README for stale descriptions — not just version numbers
- **Project structure, file-level details, and internal architecture belong in `docs/DOCUMENTATION-GUIDE.md`**, not the README
- When in doubt, update it — a stale README is worse than a slightly verbose one

---

## 9. Git Commit Messages

### Format
`v<VERSION>: Short description of what changed`

Examples:
- `v0.1: Baseline - initial working compliance gap analyzer`
- `v0.1: Add dev logs, version-tagged reports, and documentation system`
- `v0.2: Fix format_search_results bug and add error handling`

### Rules
- One commit per logical change or per work session
- The commit message describes the "what" — the iteration doc and dev log describe the "why"
- **After completing documentation updates, the agent should suggest a commit message** following the format above. This is typically the last step before the user commits and pushes.

### Suggested Commit Message Template

After logging and updating all documentation, suggest a commit message like:

```
v<VERSION>: <what changed in code> + docs
```

Examples by session type:
- **Code changes only:** `v0.2: Fix format_search_results bug and add error handling`
- **Code + tests:** `v0.2: Add test scenarios, timing, and observability logging`
- **Docs only (mid-version):** `v0.2: Update iteration doc and changelog for session 2`
- **Full session (code + docs):** `v0.2: Add timing and test log + docs update`

If a session spans multiple concerns, summarize the biggest changes -- don't list everything. The iteration doc and dev log have the details.

---

## 10. Version Management

The current version is defined in two places in code:
1. The `version` default parameter in `run_analysis()` inside `agent.py`
2. The `VERSION` constant in `streamlit_app.py`

Both must be updated together when bumping versions.

### How to Bump the Version
When the user says "let's start v0.X", the agent should:
1. Update the default `version` parameter in `run_analysis()` in `agent.py`
2. Update the `VERSION` constant in `streamlit_app.py`
3. Create a new iteration doc: `docs/iterations/v<NEW>-<description>.md`
4. Add a new entry to `CHANGELOG.md`

### Version Numbering
- `v0.1`, `v0.2`, `v0.3`... — incremental improvements
- Each version represents a batch of related changes (bug fixes, new feature, etc.)
- The user decides when to bump — the agent should ask if unsure

---

## 11. Workflow for Each New Version

1. Review the previous version's "Remaining Issues" section
2. Create `docs/iterations/v0.X-description.md` with Goal section
3. Make code changes — update the iteration doc as you go
4. Run tests — add Test Results to the iteration doc
5. Update CHANGELOG.md with version summary
6. Update README.md — version status, known issues, roadmap, structure (see Section 8)
7. Update `docs/PROJECT-SCHEMA.md` if any strategic decisions were made (see Section 7)
8. Write dev log summary for the chat session
9. User exports chat transcript from Cursor
10. Agent suggests a commit message (see Section 9)
11. Commit and push to `dev` (see `docs/BRANCHING-GUIDE.md` for full workflow):
   ```powershell
   git checkout dev
   git add .
   git commit -m "v0.X: description"
   git push origin dev
   ```
12. When version is tested and stable, merge `dev → main` via Pull Request (see Branching Guide)

---

## For AI Agents: Quick Reference

When starting a new chat on this project:
1. Read this file first
2. Read the latest `docs/iterations/v0.X-*.md` to understand current state
3. Read `CHANGELOG.md` for version history overview
4. Read `docs/PROJECT-SCHEMA.md` for the project vision and strategic direction
5. Follow all naming conventions and file structures above
6. At the end of the session, write a dev log summary in `docs/dev-logs/`
7. Update the iteration doc with any new findings or test results
8. Update `README.md` if version, known issues, roadmap, or project structure changed
9. Update `docs/PROJECT-SCHEMA.md` if any strategic decisions were made during the session
