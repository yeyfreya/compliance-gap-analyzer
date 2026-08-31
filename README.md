# AI Compliance Gap Analyzer

**Quickly see the potential compliance gaps between your AI technology and your industry's regulatory requirements.**

Built for teams whose compliance obligations are real and ongoing: past the point where you can defer them, not yet big enough to justify a compliance department. Describe your AI use case, your tech stack, and your industry — the agent maps which regulations plausibly apply, researches them against the regulators' own sources, cross-references them with your technology's obligations, and delivers a clear, scannable gap report in a few minutes.

> **[Try the Live Demo →](https://ai-compliance-gap-analyzer.streamlit.app/)**
>
> No sign-up. No API keys. Just pick a scenario or enter your own.

![AI Compliance Gap Analyzer — live demo screenshot](assets/screenshot.jpg)

---

## What You Get

A structured compliance gap report covering:

- **Scope & Assumptions** — who the analysis assumed you are, what it inferred rather than knew, and what would change if an assumption is wrong
- **Compliance Gap Matrix** — executive summary table with each potential gap, risk level, regulatory basis, and recommended action
- **Key Regulatory Landscape** — which frameworks and requirements apply to your case
- **Gap Details** — what each gap means and why it matters, framed as areas worth confirming (never assumptions about what you have or haven't done)
- **Recommended Next Steps** — grouped by priority so you know where to start
- **Coverage** — what was considered, what was ruled out *and why*, and which authoritative sources were actually searched
- **Bottom Line** — a concise takeaway you can act on immediately

Every source is labelled by tier — whether it came from a regulator's or standards body's own
site, or from secondary commentary — so you can see what each finding rests on.

Reports use a warm, supportive tone — like a knowledgeable friend pointing out things you might want to look into, not an auditor issuing violations.

> Showcase reports are included in the repo — see [`reports/`](reports/) for examples across healthcare, fintech, and RegTech.

---

## How It Works

```
   ┌───────────────┐    ┌───────────────┐    ┌───────────────┐    ┌───────────────┐
   │  You provide  │───▶│  Agent scopes │───▶│ Agent researches │─▶│  Agent writes │
   │  3 inputs     │    │  the territory│    │  official sources │  │  your report  │
   └───────────────┘    └───────────────┘    └───────────────┘    └───────────────┘
                               │                      │                    │
                     jurisdiction, profession,   authoritative        gaps, assumptions
                     data, activity, vendor      domains first        and coverage
                                                                            │
                                                                            ▼
                                                                Compliance gap report
                                                                typically 2–3 minutes
```

**Why the scoping step exists.** Before any searching, the agent maps the regulatory territory
across five fixed dimensions — which jurisdictions apply, which professional body governs the
field, what data is handled, what the AI actually does, and whose technology processes it. That
map decides what gets researched, so coverage comes from the dimensions rather than from
whichever queries happened to be invented. It also produces the list of authoritative domains
for your specific scenario, which is what makes official-source-first research possible.

---

## Example

**Input:**
- Use case: "AI-powered resume screening tool"
- Technology: "OpenAI GPT-4 API"
- Industry: "Enterprise HR (US-based)"

**What the report covers:**
- Employment discrimination law (Title VII, ADA, state AI hiring laws)
- AI transparency and explainability requirements
- Data privacy obligations (CCPA, EEOC guidance)
- Vendor-specific compliance (OpenAI's usage policies for HR decisions)
- Bias testing and adverse impact analysis gaps

---

## What's Coming Next

- Consistent report structure enforcement (full template)
- PDF report generation
- Research adequacy loop (agent validates its own research before writing)
- Plugin version for AI agent platforms (OpenClaw and similar)

---

## Run It Locally

### Prerequisites

- Python 3.14+
- [Anthropic API key](https://console.anthropic.com/)
- [Tavily API key](https://tavily.com/)

### Setup

```bash
git clone https://github.com/yeyfreya/ai-compliance-gap-analyzer.git
cd ai-compliance-gap-analyzer

python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

pip install -r requirements.txt
```

Create a `.env` file in the project root:

```
ANTHROPIC_API_KEY = <your-anthropic-key>
TAVILY_API_KEY   = <your-tavily-key>
```

### Web UI

```bash
python -m streamlit run streamlit_app.py
```

Opens at `http://localhost:8501`. Pick a preset scenario or enter custom inputs, then click **Run Analysis**.

### CLI

```bash
python agent.py <scenario>
```

Available scenarios:

```bash
python agent.py hr          # AI resume screening — US employment law
python agent.py healthcare  # AI diagnostics — HIPAA, FDA
python agent.py fintech     # AI credit scoring — UK FCA, GDPR
python agent.py education   # AI essay grading — FERPA, COPPA
python agent.py regtech     # AI compliance analyzer — RegTech SaaS
```

---

## Built With

Claude Sonnet 4.5 (Anthropic) · Tavily · Langfuse · Supabase · Streamlit · Python

---

## Current Status

**v0.7** — Active development. See [ARCHITECTURE.md](docs/ARCHITECTURE.md) for technical decisions.

**Known limitations** — this tool highlights areas worth reviewing; it is not legal advice, and
every report says so:
- Analysis typically takes 2–3 minutes, longer for complex or multi-jurisdiction cases
- **Results vary between runs.** The set of regulations considered is stable, but which one is
  ranked most urgent can differ when the same inputs are run twice
- **Source tiering is not airtight.** Research prefers regulators' and standards bodies' own
  sites, but the search provider's domain filter is not strict, so some secondary commentary
  can still be labelled as an official source
- Verify anything you act on against the primary source — the report lists which authoritative
  domains were searched so you can check its work

See [CHANGELOG.md](CHANGELOG.md) for version history and [docs/iterations/](docs/iterations/) for detailed analysis per version.

---

## Contributing

See the [project structure](docs/DOCUMENTATION-GUIDE.md) and [branching guide](docs/BRANCHING-GUIDE.md) for how the codebase and git workflow are organized.

---

## Author

**Freya Ye Yu** — [LinkedIn](https://www.linkedin.com/in/yeyufreya/) · [Portfolio](https://www.yeyufreya.com/)

MIT License
