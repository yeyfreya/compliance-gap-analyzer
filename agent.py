"""
AI Compliance Gap Analyzer - Main Agent
Orchestrates research and analysis workflow.
"""

import os
import re
import json
import time
import csv
from datetime import datetime
import anthropic
from dotenv import load_dotenv
from langfuse import observe, get_client as get_langfuse_client
from opentelemetry.instrumentation.anthropic import AnthropicInstrumentor

from tools import search_web, format_search_results
from prompts import SYSTEM_PROMPT, ANALYSIS_PROMPT, SCOPING_PROMPT, REPORT_DISCLAIMER

load_dotenv()

# Initialize Langfuse (reads LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST from env)
langfuse = get_langfuse_client()
AnthropicInstrumentor().instrument()

# Initialize Claude client
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def _today() -> str:
    """Today's date, written out for a prompt (e.g. "7 August 2026").

    Both Claude calls need this. Without it the model falls back on its training-era sense
    of "now": the planner searches for the wrong year, and the analysis repeats deadlines
    that have since moved. Resolved per call, never cached, so a long-running Streamlit
    process doesn't get stuck on the date it booted.
    """
    return datetime.now().strftime("%d %B %Y").lstrip("0")


class EmptyResearchError(Exception):
    """Raised when research returns zero results.

    Signals that we must NOT ask Claude to write a report, because a report built on
    no research would be fabricated (#29). Callers decide how to surface this.
    """


class ScopingError(Exception):
    """Raised when the scoping step fails to produce usable JSON after a retry.
    The pipeline aborts honestly rather than falling back to the v0.6 planner,
    which failed its accuracy test."""


def _retry_api_call(fn, max_retries=1, backoff_sec=2.0):
    """Call fn(), retry once on transient API errors with exponential backoff.

    Retries on: rate limits, overloaded, timeouts, connection errors.
    Does NOT retry on: auth errors, invalid requests, or non-API exceptions.
    Returns the result of fn() on success, or re-raises the last exception.
    """
    last_exc = None
    for attempt in range(1 + max_retries):
        try:
            return fn()
        except anthropic.RateLimitError as e:
            last_exc = e
        except anthropic.InternalServerError as e:
            last_exc = e
        except anthropic.APIConnectionError as e:
            last_exc = e
        except anthropic.APITimeoutError as e:
            last_exc = e
        except Exception:
            raise

        wait = backoff_sec * (2 ** attempt)
        print(f"⚠️ API call failed (attempt {attempt + 1}/{1 + max_retries}), retrying in {wait}s…")
        time.sleep(wait)

    raise last_exc


# Function 1: scope_analysis() - Map the regulatory territory before any research runs
@observe()
def scope_analysis(use_case: str, technology: str, industry: str) -> dict:
    """
    Ask Claude to map the regulatory territory across five fixed dimensions
    (jurisdiction, profession, data, activity, vendor), with extended thinking enabled.
    Runs BEFORE any research — its output drives gather_research()'s tiered, per-regime
    searches. Replaces v0.6's free-form plan_searches().

    Returns:
        dict with keys: scope (dict), thinking (str), tokens_in (int), tokens_out (int)

    Raises:
        ScopingError: if the API call itself errors, or scoping still fails to produce
        usable JSON after one retry. There is NO fallback path here — a report built on
        a guessed scope is exactly the failure mode that sank v0.6's planner.
    """
    print("\n🧭 Scoping regulatory territory...")

    prompt = SCOPING_PROMPT.format(
        current_date=_today(),
        use_case=use_case,
        technology=technology,
        industry=industry
    )

    def _call():
        return client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=6000,
            thinking={"type": "enabled", "budget_tokens": 3000},
            system=SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

    def _extract(response):
        thinking_text = ""
        response_text = ""
        for block in response.content:
            if block.type == "thinking":
                thinking_text = block.thinking
            elif block.type == "text":
                response_text = block.text
        return thinking_text, response_text

    def _parse(response_text: str) -> dict:
        start = response_text.find('{')
        end = response_text.rfind('}') + 1
        parsed = json.loads(response_text[start:end])
        if not isinstance(parsed.get("candidate_regimes"), list) or not parsed["candidate_regimes"]:
            raise ValueError("candidate_regimes missing or empty")
        if not isinstance(parsed.get("official_domains"), list):
            raise ValueError("official_domains missing or not a list")
        return parsed

    try:
        response = _retry_api_call(_call)
    except anthropic.APIError as e:
        raise ScopingError(f"Claude API error during scoping: {e}") from e

    thinking_text, response_text = _extract(response)
    tokens_in = response.usage.input_tokens
    tokens_out = response.usage.output_tokens

    try:
        scope = _parse(response_text)
    except (json.JSONDecodeError, ValueError, IndexError) as first_err:
        print(f"⚠️ Couldn't parse scoping output ({first_err}), retrying once...")
        try:
            response = _retry_api_call(_call)
        except anthropic.APIError as e:
            raise ScopingError(f"Claude API error during scoping retry: {e}") from e

        thinking_text, response_text = _extract(response)
        tokens_in = response.usage.input_tokens
        tokens_out = response.usage.output_tokens

        try:
            scope = _parse(response_text)
        except (json.JSONDecodeError, ValueError, IndexError) as second_err:
            raise ScopingError(
                f"Scoping failed to produce usable JSON after retry: {second_err}"
            ) from second_err

    print(f"✅ Scoped {len(scope['candidate_regimes'])} candidate regulations")
    return {
        "scope": scope,
        "thinking": thinking_text,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
    }


# ── Source tiering (v0.7) ────────────────────────────────────────────────────
# Tier 1 = the authority's own domain (regulator, standards body, vendor docs) — search
# restricted to scope["official_domains"]. Tier 2 = the unrestricted fallback used only
# when Tier 1 comes back empty. Every source the pipeline surfaces carries a tier tag so
# ANALYSIS_PROMPT can weight claims accordingly (see prompts.py "SOURCE TIERS").
def _tag_tier(formatted_block: str, tier: int) -> str:
    """Prefix each result block in a format_search_results() string with its tier tag."""
    tag = "[TIER 1 — official source]" if tier == 1 else "[TIER 2 — commentary]"
    return re.sub(r'--- Result (\d+) ---', rf'--- Result \1 {tag} ---', formatted_block)


# ── Research adequacy (#7) ────────────────────────────────────────────────────
# Below this many total results, research is considered "thin" and triggers ONE
# broadened supplementary search round. A cheap heuristic, not an LLM-driven loop.
MIN_ADEQUATE_RESULTS = 4


def _broadened_queries(use_case: str, technology: str, industry: str) -> list:
    """Generic, broad fallback queries for the #7 supplementary search round.

    Deliberately broad so they are likely to return *something* even when the
    scoped regime queries were too narrow, too specific, or mistyped.
    """
    return [
        f"{industry} AI compliance regulations",
        f"{technology} data privacy compliance",
        f"AI regulation requirements {industry}",
    ]


def _run_broadened_round(use_case: str, technology: str, industry: str) -> dict:
    """Supplementary, unrestricted search round for #7 (thin research).

    Bypasses the tiered, per-regime scoping entirely, so every result is tagged
    tier 2 / regime "general" — same result shape as gather_research().
    """
    all_text = []
    sources = []
    successful_queries = []
    failed_queries = []
    executed_queries = []

    for query in _broadened_queries(use_case, technology, industry):
        executed_queries.append(query)
        search_response = search_web(query, max_results=3)
        results = search_response.get('results', [])

        if results:
            successful_queries.append(query)
            all_text.append("\n=== Rulebook: general (status: supplementary) ===")
            all_text.append(_tag_tier(format_search_results(results), 2))
            for r in results:
                sources.append({
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "query": query,
                    "tier": 2,
                    "regime": "general",
                })
        else:
            failed_queries.append(query)

    return {
        "findings_text": "\n".join(all_text),
        "sources": sources,
        "successful_queries": successful_queries,
        "failed_queries": failed_queries,
        "executed_queries": executed_queries,
        "num_results": len(sources),
        "tier1_count": 0,
        "tier2_count": len(sources),
        "regimes_searched": [],
        "domains_searched": [],
    }


def _merge_research(first: dict, second: dict) -> dict:
    """Combine two gather_research()-shaped results into one, de-duplicating sources by URL."""
    seen_urls = {s["url"] for s in first["sources"] if s["url"]}
    merged_sources = list(first["sources"])
    for s in second["sources"]:
        if s["url"] and s["url"] in seen_urls:
            continue
        seen_urls.add(s["url"])
        merged_sources.append(s)

    findings = "\n".join(
        text for text in [first["findings_text"], second["findings_text"]] if text
    )

    return {
        "findings_text": findings,
        "sources": merged_sources,
        "successful_queries": first["successful_queries"] + second["successful_queries"],
        "failed_queries": first["failed_queries"] + second["failed_queries"],
        "executed_queries": first.get("executed_queries", []) + second.get("executed_queries", []),
        "num_results": len(merged_sources),
        "tier1_count": first.get("tier1_count", 0) + second.get("tier1_count", 0),
        "tier2_count": first.get("tier2_count", 0) + second.get("tier2_count", 0),
        "regimes_searched": first.get("regimes_searched", []) + second.get("regimes_searched", []),
        "domains_searched": first.get("domains_searched", []),
    }


# Function 2: gather_research() - Tiered, per-regime search driven by the scoping output
@observe()
def gather_research(use_case: str, technology: str, industry: str, scope: dict) -> dict:
    """
    Run tiered research for each candidate regime from scope_analysis().

    For every regime marked "likely_applies" or "may_apply" (excluded regimes still
    reach the report via the scoping data itself, not via research): Tier 1 searches
    scope["official_domains"] only; if that returns nothing, Tier 2 falls back to an
    unrestricted search. If the combined results are still thin, runs ONE broadened
    supplementary round (#7) and merges it in.

    Args:
        scope: the dict returned by scope_analysis()["scope"]

    Returns:
        dict with keys:
            findings_text (str): formatted research text for Claude, tier-tagged per result
            sources (list[dict]): {"title", "url", "query", "tier", "regime"} per result
            successful_queries (list[str]): queries that returned at least one result
            failed_queries (list[str]): queries where both tiers returned nothing
            executed_queries (list[str]): every query actually run, in order
            num_results (int): total number of results across all regimes
            tier1_count (int): results that came from an official-domain-restricted search
            tier2_count (int): results that came from an unrestricted fallback search
            regimes_searched (list[str]): regime names actually searched
            domains_searched (list[str]): official_domains actually passed to Tier 1
    """
    print("\n🔬 Conducting tiered research...")

    regimes = scope.get("candidate_regimes", [])[:8]
    searchable = [r for r in regimes if r.get("status") in ("likely_applies", "may_apply")]
    official_domains = scope.get("official_domains", [])

    all_text = []
    sources = []
    successful_queries = []
    failed_queries = []
    executed_queries = []
    regimes_searched = []
    tier1_count = 0
    tier2_count = 0

    for regime in searchable:
        query = regime.get("search_query", "")
        name = regime.get("name", "Unnamed regulation")
        status = regime.get("status", "")
        if not query:
            continue

        executed_queries.append(query)
        regimes_searched.append(name)

        tier1_response = search_web(query, max_results=3, include_domains=official_domains)
        tier1_results = tier1_response.get('results', [])

        if tier1_results:
            tier = 1
            results = tier1_results
        else:
            tier2_response = search_web(query, max_results=3)
            results = tier2_response.get('results', [])
            tier = 2

        if results:
            successful_queries.append(query)
            all_text.append(f"\n=== Rulebook: {name} (status: {status}) ===")
            all_text.append(_tag_tier(format_search_results(results), tier))
            for r in results:
                sources.append({
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "query": query,
                    "tier": tier,
                    "regime": name,
                })
            if tier == 1:
                tier1_count += len(results)
            else:
                tier2_count += len(results)
        else:
            # Both tiers came back empty — record it so the pipeline can react
            failed_queries.append(query)

    research = {
        "findings_text": "\n".join(all_text),
        "sources": sources,
        "successful_queries": successful_queries,
        "failed_queries": failed_queries,
        "executed_queries": executed_queries,
        "num_results": len(sources),
        "tier1_count": tier1_count,
        "tier2_count": tier2_count,
        "regimes_searched": regimes_searched,
        "domains_searched": official_domains,
    }

    if research["num_results"] < MIN_ADEQUATE_RESULTS:
        print(
            f"\n🔁 Research looks thin ({research['num_results']} results) — "
            "running one broadened search round…"
        )
        supplementary = _run_broadened_round(use_case, technology, industry)
        research = _merge_research(research, supplementary)

    return research


def score_research_quality(
    num_sources: int,
    research_limited: bool,
    num_failed_queries: int,
    num_candidate_regimes: int,
    pct_tier1_sources: float,
) -> None:
    """Attach research-quality scores to the current Langfuse trace so runs are filterable.

    Must be called from inside an @observe-decorated function (so a trace is active).
    These become filterable/chartable "scores" in the Langfuse UI.

    Two robustness details for the v4 SDK in a long-running Streamlit process:
    - Scores are attached to the trace by its explicit id (create_score) rather than relying
      on the ambient "current" context.
    - flush() is called so the scores are sent immediately. Without it, scores sit buffered
      until the process exits — which never happens in a live Streamlit app.

    Args:
        num_candidate_regimes: how many regulations/standards scope_analysis() surfaced
        pct_tier1_sources: fraction (0–1) of sources that came from an official domain

    Fail-safe: any Langfuse error is swallowed so observability never breaks the pipeline.
    """
    try:
        trace_id = langfuse.get_current_trace_id()
        if not trace_id:
            return
        langfuse.create_score(name="num_sources", value=num_sources,
                              trace_id=trace_id, data_type="NUMERIC")
        langfuse.create_score(name="research_limited", value=1 if research_limited else 0,
                              trace_id=trace_id, data_type="BOOLEAN")
        langfuse.create_score(name="num_failed_queries", value=num_failed_queries,
                              trace_id=trace_id, data_type="NUMERIC")
        langfuse.create_score(name="num_candidate_regimes", value=num_candidate_regimes,
                              trace_id=trace_id, data_type="NUMERIC")
        langfuse.create_score(name="pct_tier1_sources", value=pct_tier1_sources,
                              trace_id=trace_id, data_type="NUMERIC")
        langfuse.flush()  # push scores out now; a live Streamlit app never shuts down to flush
    except Exception as e:
        print(f"⚠️ Langfuse research-quality scoring skipped: {e}")


# Function 3: analyze_compliance() - Ask Claude to analyze
@observe()
def analyze_compliance(
    use_case: str,
    technology: str,
    industry: str,
    research_findings: str,
    scope: dict,
    domains_searched: list,
) -> dict:
    """
    Analyze compliance gaps based on tiered research and the earlier scoping output,
    with extended thinking enabled.

    Args:
        scope: the dict returned by scope_analysis()["scope"] — carries assumptions and
            candidate_regimes so the report can show its own scoping honestly
        domains_searched: the official_domains actually passed to Tier 1 searches, so the
            report's "Official sources searched" line is truthful, never invented

    Returns:
        dict with keys: analysis (str), thinking (str), tokens_in (int), tokens_out (int)
    """
    print("\n🧠 Analyzing compliance gaps...")

    scoping_context = json.dumps({
        "assumptions": scope.get("assumptions", []),
        "candidate_regimes": scope.get("candidate_regimes", []),
    }, indent=2)
    official_domains_searched = "\n".join(f"- {d}" for d in domains_searched) or "(none)"

    prompt = ANALYSIS_PROMPT.format(
        current_date=_today(),
        use_case=use_case,
        technology=technology,
        industry=industry,
        scoping_context=scoping_context,
        official_domains_searched=official_domains_searched,
        research_findings=research_findings
    )

    try:
        response = _retry_api_call(lambda: client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=8000,
            thinking={"type": "enabled", "budget_tokens": 4000},
            system=SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": prompt}
            ]
        ))
    except anthropic.APIError as e:
        print(f"❌ Claude API error during analysis: {e}")
        return {
            "analysis": f"[Analysis failed: Claude API returned an error — {e}. Research data was collected successfully. Please retry.]",
            "thinking": None,
            "tokens_in": 0,
            "tokens_out": 0,
            "error": f"analyze_compliance API error: {e}",
        }

    thinking_text = ""
    analysis_text = ""
    for block in response.content:
        if block.type == "thinking":
            thinking_text = block.thinking
        elif block.type == "text":
            analysis_text = block.text

    return {
        "analysis": analysis_text,
        "thinking": thinking_text,
        "tokens_in": response.usage.input_tokens,
        "tokens_out": response.usage.output_tokens,
    }


# Function 4: save_report() - Persist results to a file
def save_report(result: dict, version: str = "v0.7", output_dir: str | None = None, run_id: str | None = None) -> str:
    """
    Save the analysis report to a timestamped file named after the use case.

    Args:
        result: Dictionary returned by run_analysis()
        version: Code version tag (e.g., "v0.1", "v0.2")
        output_dir: Directory to save in (defaults to this script's directory)
        run_id: Supabase analysis_runs UUID for cross-referencing

    Returns:
        Path to the saved report file
    """
    if output_dir is None:
        output_dir = os.path.dirname(os.path.abspath(__file__))

    reports_dir = os.path.join(output_dir, "reports")
    os.makedirs(reports_dir, exist_ok=True)

    slug = re.sub(r'[^a-z0-9]+', '-', result['use_case'].lower()).strip('-')[:30].rstrip('-')
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"report_{version}_{timestamp}_{slug}.md"
    filepath = os.path.join(reports_dir, filename)

    timing = result.get('timing', {})
    timing_line = ""
    if timing:
        timing_line = (
            f"**Generation Time:** {timing['total_sec']}s total "
            f"(scoping: {timing['scoping_sec']}s, "
            f"research: {timing['research_sec']}s, "
            f"analysis: {timing['analysis_sec']}s)  \n"
        )

    run_id_line = f"**Run ID:** `{run_id}`  \n" if run_id else ""

    # Honest note when the report was built on thin research (#29)
    limited_note = ""
    if result.get("research_limited"):
        limited_note = (
            "> ⚠️ **Note:** This report was generated from limited research data. "
            "Some searches returned few or no results, so coverage may be incomplete — "
            "consider re-running the analysis.\n\n"
        )

    header = (
        f"# Compliance Gap Analysis Report\n\n"
        f"**Version:** {version}  \n"
        f"{run_id_line}"
        f"**Use Case:** {result['use_case']}  \n"
        f"**Technology:** {result['technology']}  \n"
        f"**Industry:** {result['industry']}  \n"
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  \n"
        f"{timing_line}\n"
        f"---\n\n"
        f"{limited_note}"
        f"## Search Queries Used\n\n"
    )
    queries_section = "\n".join(f"- {q}" for q in result['search_queries']) + "\n\n"
    body = f"---\n\n## Analysis\n\n{result['analysis']}\n"

    # Sources section — shows where the research came from (#14)
    sources = result.get("sources", [])
    sources_section = ""
    if sources:
        lines = [
            "\n---\n",
            "## Sources\n",
            "_Regulatory and policy sources the agent reviewed for this report._\n",
        ]
        for i, s in enumerate(sources, 1):
            title = s.get("title") or s.get("url") or "Untitled source"
            url = s.get("url", "")
            line = f"{i}. [{title}]({url})" if url else f"{i}. {title}"
            tier = s.get("tier")
            if tier == 1:
                line += " — official source"
            elif tier == 2:
                line += " — commentary"
            lines.append(line)
        sources_section = "\n".join(lines) + "\n"

    # Fine print — every report carries it, no exceptions (see REPORT_DISCLAIMER)
    disclaimer_section = f"\n---\n\n{REPORT_DISCLAIMER}\n"

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(header + queries_section + body + sources_section + disclaimer_section)

    print(f"\n💾 Report saved to: {filepath}")
    return filepath


# Function 5: run_analysis() - Orchestrate everything
@observe()
def run_analysis(use_case: str, technology: str, industry: str, version: str = "v0.7") -> dict:
    """
    Main function to run complete compliance gap analysis.

    Returns dict with: use_case, technology, industry, search_queries, analysis,
    timing, scoping_thinking, analysis_thinking, token_usage, scope, tier1_count,
    tier2_count, domains_searched.
    """
    inputs = {"use_case": use_case, "technology": technology, "industry": industry}
    for field, value in inputs.items():
        if not value or not value.strip():
            return {"error": f"Missing required field: {field}"}
        if len(value) > 500:
            return {"error": f"Field '{field}' exceeds 500 character limit ({len(value)} chars)"}

    print("\n" + "="*60)
    print("🚀 AI COMPLIANCE GAP ANALYZER")
    print("="*60)

    print(f"\nUse Case: {use_case}")
    print(f"Technology: {technology}")
    print(f"Industry: {industry}")

    total_start = time.time()

    # Step 1: Scope the regulatory territory (returns dict with scope, thinking, tokens)
    t0 = time.time()
    try:
        scope_result = scope_analysis(use_case, technology, industry)
    except ScopingError as e:
        print(f"\n❌ Scoping failed — aborting before research. {e}")
        return {"error": f"Scoping failed: {e}. Please try again."}
    scope = scope_result["scope"]
    time_scoping = time.time() - t0

    # Step 2: Gather tiered, per-regime research (with lightweight adequacy retry — #7)
    t0 = time.time()
    research = gather_research(use_case, technology, industry, scope)
    research_findings = research["findings_text"]
    time_research = time.time() - t0

    search_queries = research.get(
        "executed_queries", research["successful_queries"] + research["failed_queries"]
    )

    # #29 — refuse to write a report on top of empty research (it would be fabricated)
    if research["num_results"] == 0:
        print("\n❌ Research returned no results — aborting before analysis to avoid a fabricated report.")
        return {
            "error": (
                "Research failed: no results were returned from any search. "
                "This is usually a transient web-search issue — please try again."
            )
        }

    # Partial research: enough to proceed, but thin enough to flag in the report (#29)
    research_limited = 0 < research["num_results"] < MIN_ADEQUATE_RESULTS

    # Record research-quality scores on the Langfuse trace so runs are filterable
    pct_tier1_sources = research["tier1_count"] / max(research["num_results"], 1)
    score_research_quality(
        research["num_results"], research_limited, len(research["failed_queries"]),
        len(scope.get("candidate_regimes", [])), pct_tier1_sources,
    )

    # Step 3: Analyze compliance (returns dict with analysis, thinking, tokens)
    t0 = time.time()
    analysis_result = analyze_compliance(
        use_case, technology, industry, research_findings, scope, research["domains_searched"]
    )
    analysis = analysis_result["analysis"]
    time_analysis = time.time() - t0

    time_total = time.time() - total_start

    timing = {
        'scoping_sec': round(time_scoping, 1),
        'research_sec': round(time_research, 1),
        'analysis_sec': round(time_analysis, 1),
        'total_sec': round(time_total, 1),
    }

    print("\n" + "="*60)
    print("✅ ANALYSIS COMPLETE")
    print(f"⏱️  Total: {timing['total_sec']}s "
          f"(scoping: {timing['scoping_sec']}s, "
          f"research: {timing['research_sec']}s, "
          f"analysis: {timing['analysis_sec']}s)")
    print("="*60)

    result = {
        'use_case': use_case,
        'technology': technology,
        'industry': industry,
        'search_queries': search_queries,
        'analysis': analysis,
        'sources': research["sources"],
        'research_limited': research_limited,
        'timing': timing,
        'scoping_thinking': scope_result.get("thinking"),
        'analysis_thinking': analysis_result.get("thinking"),
        'token_usage': {
            'scoping': {'input': scope_result.get("tokens_in", 0), 'output': scope_result.get("tokens_out", 0)},
            'analysis': {'input': analysis_result.get("tokens_in", 0), 'output': analysis_result.get("tokens_out", 0)},
        },
        'scope': scope,
        'tier1_count': research["tier1_count"],
        'tier2_count': research["tier2_count"],
        'domains_searched': research["domains_searched"],
    }

    report_path = save_report(result, version=version)
    append_test_log(result, version=version, report_path=report_path)
    return result


# Function 6: append_test_log() - Track performance across runs

_TEST_LOG_FIELDS = [
    'timestamp', 'version', 'run_id', 'use_case', 'technology', 'industry',
    'num_queries', 'scoping_sec', 'planning_sec', 'research_sec', 'analysis_sec', 'total_sec',
    'report_file',
]


def append_test_log(result: dict, version: str, report_path: str, run_id: str | None = None) -> None:
    """Append one row to reports/test-log.csv after every successful run."""
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "test-log.csv")

    timing = result.get('timing', {})
    row = {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'version': version,
        'run_id': run_id or '',
        'use_case': result['use_case'],
        'technology': result['technology'],
        'industry': result['industry'],
        'num_queries': len(result.get('search_queries', [])),
        'scoping_sec': timing.get('scoping_sec', ''),
        'planning_sec': '',  # v0.6 column, kept for old-row compatibility — v0.7 runs leave it empty
        'research_sec': timing.get('research_sec', ''),
        'analysis_sec': timing.get('analysis_sec', ''),
        'total_sec': timing.get('total_sec', ''),
        'report_file': os.path.basename(report_path),
    }

    if os.path.exists(log_path):
        with open(log_path, 'r', encoding='utf-8') as f:
            existing_header = f.readline().strip().split(',')
        if existing_header != _TEST_LOG_FIELDS:
            _migrate_csv_header(log_path)

    file_exists = os.path.exists(log_path)
    with open(log_path, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=_TEST_LOG_FIELDS)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)

    print(f"📊 Test log updated: {log_path}")


def _migrate_csv_header(log_path: str) -> None:
    """Migration: bring an existing test-log.csv header up to date with _TEST_LOG_FIELDS,
    filling any newly added columns with '' on old rows (started as a run_id-only add,
    generalized in v0.7 for scoping_sec)."""
    with open(log_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        old_rows = list(reader)

    with open(log_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=_TEST_LOG_FIELDS, extrasaction='ignore')
        writer.writeheader()
        for old_row in old_rows:
            for field in _TEST_LOG_FIELDS:
                old_row.setdefault(field, '')
            writer.writerow(old_row)


# Test scenarios
TEST_SCENARIOS = {
    "hr": {
        "use_case": "AI-powered resume screening tool",
        "technology": "OpenAI GPT-4 API",
        "industry": "Enterprise HR tech (US-based)",
    },
    "healthcare": {
        "use_case": "AI diagnostic assistant that analyzes medical images and suggests diagnoses",
        "technology": "Google Gemini API",
        "industry": "US hospital network (healthcare)",
    },
    "fintech": {
        "use_case": "AI credit scoring model that evaluates loan applications",
        "technology": "AWS SageMaker",
        "industry": "UK neobank (financial services)",
    },
    "education": {
        "use_case": "AI essay grading and feedback tool for student assignments",
        "technology": "Anthropic Claude API",
        "industry": "US K-12 school district (education)",
    },
    "regtech": {
        "use_case": "AI agent powered compliance gap analyzer",
        "technology": "Anthropic Claude Sonnet 4.5",
        "industry": "RegTech / AI compliance SaaS — serving early-stage AI startups",
    },
}

def _parse_cli_args(argv: list) -> dict:
    """Resolve command-line arguments into a scenario dict for run_analysis().

    Two ways to run:
      python agent.py healthcare
      python agent.py --use-case "…" --technology "…" --industry "…"

    The second form exists so one-off analyses can be run without adding anyone's real
    business details to this file — which lives in a public repo. Custom inputs stay in
    the shell, not in source control.

    Exits with usage text if the arguments don't form a complete scenario.
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="python agent.py",
        description="Run a compliance gap analysis from a named scenario or custom inputs.",
    )
    parser.add_argument("scenario", nargs="?", choices=sorted(TEST_SCENARIOS),
                        help="one of the built-in test scenarios")
    parser.add_argument("--use-case", help="what the AI system does (custom run)")
    parser.add_argument("--technology", help="the model or platform it runs on (custom run)")
    parser.add_argument("--industry", help="the industry and jurisdiction (custom run)")
    args = parser.parse_args(argv)

    custom = {"use_case": args.use_case, "technology": args.technology, "industry": args.industry}
    given = [name for name, value in custom.items() if value]

    if args.scenario and given:
        parser.error("use either a scenario name or the custom flags, not both")

    if args.scenario:
        return TEST_SCENARIOS[args.scenario]

    if given:
        missing = [name for name, value in custom.items() if not value]
        if missing:
            parser.error("a custom run needs all three: " + ", ".join(f"--{m.replace('_', '-')}" for m in missing))
        return custom

    parser.print_help()
    print("\nAvailable scenarios:")
    for key, s in TEST_SCENARIOS.items():
        print(f"  {key:12s} -- {s['use_case']}")
    raise SystemExit(1)


if __name__ == "__main__":
    import sys

    result = run_analysis(**_parse_cli_args(sys.argv[1:]))

    if "error" in result:
        print(f"\n❌ {result['error']}")
    else:
        print("\n" + "="*60)
        print("COMPLIANCE ANALYSIS REPORT")
        print("="*60)
        print(result['analysis'])

        # Also echo the sources here so the terminal view matches the saved report file.
        sources = result.get('sources', [])
        if sources:
            print("\n" + "-"*60)
            print(f"SOURCES ({len(sources)})")
            print("-"*60)
            for i, s in enumerate(sources, 1):
                title = s.get('title') or s.get('url') or "Untitled source"
                print(f"{i}. {title}\n   {s.get('url', '')}")