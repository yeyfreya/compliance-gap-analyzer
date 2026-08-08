"""
AI Compliance Gap Analyzer — Streamlit UI
Live demo interface for the compliance analysis pipeline.
"""

import os
import json
import streamlit as st
import streamlit.components.v1 as components
import time
from dotenv import load_dotenv

load_dotenv()

# Streamlit Cloud: inject secrets as env vars before importing agent modules,
# which create API clients at module level using os.getenv().
# Locally, .env is loaded here via dotenv. On Cloud, st.secrets are injected below.
_REQUIRED_KEYS = ("ANTHROPIC_API_KEY", "TAVILY_API_KEY")
_OPTIONAL_KEYS = ("SUPABASE_URL", "SUPABASE_KEY",
                   "LANGFUSE_SECRET_KEY", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_HOST")

_missing = []
for _key in _REQUIRED_KEYS:
    if _key not in os.environ:
        try:
            os.environ[_key] = st.secrets[_key]
        except (KeyError, FileNotFoundError):
            _missing.append(_key)

for _key in _OPTIONAL_KEYS:
    if _key not in os.environ:
        try:
            os.environ[_key] = st.secrets[_key]
        except (KeyError, FileNotFoundError):
            pass

if _missing:
    st.error(
        f"Missing API keys: **{', '.join(_missing)}**. "
        "Add them in Streamlit Cloud → Settings → Secrets (TOML format), "
        "or in a local `.env` file."
    )
    st.code('ANTHROPIC_API_KEY = "<your-anthropic-key>"\nTAVILY_API_KEY = "<your-tavily-key>"', language="toml")
    st.stop()

from langfuse import observe, get_client as get_langfuse_client
from opentelemetry import trace as otel_trace

from agent import (
    plan_searches,
    gather_research,
    analyze_compliance,
    save_report,
    append_test_log,
    score_research_quality,
    EmptyResearchError,
    MIN_ADEQUATE_RESULTS,
    TEST_SCENARIOS,
)
from prompts import REPORT_DISCLAIMER
from tracking import (
    init_session,
    start_run,
    complete_run,
    update_run_research_quality,
    log_user_event,
    save_report_to_db,
    log_error,
    mark_run_failed,
    is_rate_limited,
)

VERSION = "v0.6"
_langfuse = get_langfuse_client()

st.set_page_config(
    page_title="AI Compliance Gap Analyzer",
    page_icon="🛡️",
    layout="wide",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    .block-container { max-width: 960px; }

    /* Hero headline */
    .hero-title {
        font-size: 2rem;
        font-weight: 700;
        margin-bottom: 0.25rem;
    }
    .hero-sub {
        font-size: 1.05rem;
        opacity: 0.75;
        margin-bottom: 1.5rem;
    }

    /* Metric cards row */
    .metric-row {
        display: flex;
        gap: 1rem;
        margin-bottom: 1.5rem;
    }
    .metric-card {
        flex: 1;
        padding: 0.85rem 1rem;
        border-radius: 10px;
        background: rgba(128,128,128,0.08);
        text-align: center;
    }
    .metric-card .label { font-size: 0.78rem; opacity: 0.6; }
    .metric-card .value { font-size: 1.3rem; font-weight: 600; }

    /* Sidebar polish */
    [data-testid="stSidebar"] { min-width: 340px; }

    /* Divider */
    hr { margin: 1.5rem 0; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ── Session-state defaults ────────────────────────────────────────────────────
for key in ("result", "report_md", "report_path"):
    if key not in st.session_state:
        st.session_state[key] = None

if "supabase_session_id" not in st.session_state:
    st.session_state.supabase_session_id = init_session(
        streamlit_session_id=st.session_state.get("_st_session_id", str(id(st.session_state))),
        app_version=VERSION,
    )
    log_user_event(st.session_state.supabase_session_id, "page_load")


# ── Sidebar — inputs ─────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### Configuration")

    scenario_options = {"— Custom —": None} | {
        f"{k.title()} — {v['use_case'][:40]}": k
        for k, v in TEST_SCENARIOS.items()
    }
    chosen_label = st.selectbox("Quick-start scenario", list(scenario_options.keys()))
    chosen_key = scenario_options[chosen_label]

    if chosen_key and chosen_key != st.session_state.get("_last_scenario"):
        st.session_state._last_scenario = chosen_key
        log_user_event(st.session_state.supabase_session_id, "scenario_selected",
                       event_data={"scenario": chosen_key})

    if chosen_key:
        s = TEST_SCENARIOS[chosen_key]
        use_case = st.text_area("Use case", value=s["use_case"], height=80)
        technology = st.text_input("Technology", value=s["technology"])
        industry = st.text_input("Industry", value=s["industry"])
    else:
        use_case = st.text_area(
            "Use case",
            placeholder="e.g. AI-powered resume screening tool",
            height=80,
        )
        technology = st.text_input(
            "Technology", placeholder="e.g. OpenAI GPT-4 API"
        )
        industry = st.text_input(
            "Industry", placeholder="e.g. Enterprise HR (US-based)"
        )

    st.divider()
    run_btn = st.button("Run Analysis", type="primary", use_container_width=True)

    st.divider()
    st.caption(
        f"{VERSION} · Built with Claude + Tavily · "
        "[GitHub](https://github.com/yeyfreya/ai-compliance-gap-analyzer)"
    )


# ── Header ────────────────────────────────────────────────────────────────────
st.markdown(
    '<div class="hero-title">🛡️ AI Compliance Gap Analyzer</div>'
    '<div class="hero-sub">'
    "Enter an AI use case, technology, and industry — the agent researches "
    "regulations, identifies gaps, and generates a compliance report."
    "</div>",
    unsafe_allow_html=True,
)


# ── Pipeline function (Langfuse parent trace) ────────────────────────────────

@observe(name="compliance_pipeline")
def _run_pipeline(use_case, technology, industry, run_id, session_id, version):
    """Run the full analysis pipeline under a single Langfuse parent trace.

    All child @observe() functions (plan_searches, conduct_research,
    analyze_compliance) are automatically nested as spans under this trace.
    """
    span = otel_trace.get_current_span()
    span.set_attribute("session.id", str(session_id or ""))
    span.set_attribute("langfuse.trace.metadata", json.dumps({
        "supabase_run_id": str(run_id or ""),
        "supabase_session_id": str(session_id or ""),
        "app_version": version,
    }))
    span.set_attribute("langfuse.trace.tags", json.dumps(["streamlit", version]))

    langfuse_trace_id = _langfuse.get_current_trace_id()

    total_start = time.time()
    status_area = st.container()
    timer_slot = st.empty()

    with status_area:
        with st.status("Running compliance analysis… (step 1/3)", expanded=True) as status:

            with timer_slot.container():
                components.html(
                    """
                    <div style="display:flex; align-items:center; gap:0.6rem;
                                font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
                                padding:0.25rem 0 0.5rem; color:#FAFAFA;">
                        <span style="font-size:1.1rem;">⏱️</span>
                        <span style="font-variant-numeric:tabular-nums; font-weight:600;"
                              id="elapsed">0:00</span>
                        <span style="opacity:0.55; font-size:0.88rem;">
                            · Usually about a minute · may take longer for complex or region-specific cases
                        </span>
                    </div>
                    <script>
                        const start = Date.now();
                        const el = document.getElementById('elapsed');
                        setInterval(() => {
                            const sec = Math.floor((Date.now() - start) / 1000);
                            const m = Math.floor(sec / 60);
                            const s = sec % 60;
                            el.textContent = m + ':' + (s < 10 ? '0' : '') + s;
                        }, 1000);
                    </script>
                    """,
                    height=40,
                )

            # Step 1 — Plan searches
            st.write("📋 **Planning research strategy** — identifying key regulations to investigate…")
            t0 = time.time()
            plan_result = plan_searches(use_case, technology, industry)
            search_queries = plan_result["queries"]
            time_planning = round(time.time() - t0, 1)
            st.write(f"✅ Planned **{len(search_queries)}** search queries ({time_planning}s)")

            status.update(label="Running compliance analysis… (step 2/3)")

            # Step 2 — Conduct research (with lightweight adequacy retry — #7)
            st.write("🔬 **Conducting research** — searching the web for regulatory data…")
            t0 = time.time()
            research = gather_research(use_case, technology, industry, search_queries)
            research_findings = research["findings_text"]
            time_research = round(time.time() - t0, 1)

            # #29 — refuse to generate a report from empty research
            if research["num_results"] == 0:
                status.update(label="Research unavailable", state="error", expanded=True)
                raise EmptyResearchError("No research results were returned from any search.")

            research_limited = 0 < research["num_results"] < MIN_ADEQUATE_RESULTS
            limited_tag = " · limited data" if research_limited else ""
            st.write(
                f"✅ Research complete — {research['num_results']} sources "
                f"({time_research}s){limited_tag}"
            )

            # Record research-quality scores on this run's Langfuse trace (filterable)
            score_research_quality(
                research["num_results"], research_limited, len(research["failed_queries"])
            )

            status.update(label="Running compliance analysis… (step 3/3)")

            # Step 3 — Analyze compliance
            st.write(
                "🧠 **Analyzing compliance gaps** — the agent is cross-referencing findings "
                "and writing your report. This is the longest step…"
            )
            t0 = time.time()
            analysis_result = analyze_compliance(use_case, technology, industry, research_findings)
            analysis = analysis_result["analysis"]
            time_analysis = round(time.time() - t0, 1)
            st.write(f"✅ Analysis complete ({time_analysis}s)")

            time_total = round(time.time() - total_start, 1)
            status.update(label=f"Analysis complete — {time_total}s", state="complete", expanded=False)

    mins, secs = divmod(int(time_total), 60)
    timer_slot.markdown(f"⏱️ Report generated in **{mins}:{secs:02d}**")

    return {
        "use_case": use_case,
        "technology": technology,
        "industry": industry,
        "search_queries": search_queries,
        "analysis": analysis,
        "sources": research["sources"],
        "research_limited": research_limited,
        "num_failed_queries": len(research["failed_queries"]),
        "timing": {
            "planning_sec": time_planning,
            "research_sec": time_research,
            "analysis_sec": time_analysis,
            "total_sec": time_total,
        },
        "planning_thinking": plan_result.get("thinking"),
        "analysis_thinking": analysis_result.get("thinking"),
        "token_usage": {
            "planning": {"input": plan_result.get("tokens_in", 0), "output": plan_result.get("tokens_out", 0)},
            "analysis": {"input": analysis_result.get("tokens_in", 0), "output": analysis_result.get("tokens_out", 0)},
        },
        "langfuse_trace_id": langfuse_trace_id,
    }


# ── Run pipeline ──────────────────────────────────────────────────────────────
if run_btn:
    missing = [
        name
        for name, val in [("Use case", use_case), ("Technology", technology), ("Industry", industry)]
        if not val or not val.strip()
    ]
    if missing:
        st.error(f"Please fill in: **{', '.join(missing)}**")
        st.stop()

    session_id = st.session_state.supabase_session_id

    rate = is_rate_limited(session_id)
    if not rate["allowed"]:
        st.warning(
            f"You've used all **{rate['limit']}** free analyses for this session. "
            "Want to run more? I'd love to hear your feedback — "
            "[reach out on LinkedIn](https://www.linkedin.com/in/yeyufreya/)."
        )
        log_user_event(session_id, "rate_limited",
                       event_data={"used": rate["used"], "limit": rate["limit"]})
        st.stop()

    st.session_state.result = None
    st.session_state.report_md = None
    st.session_state.report_path = None
    st.session_state.feedback_given = False

    scenario_source = chosen_key if chosen_key else "custom"
    run_id = start_run(session_id, use_case, technology, industry, scenario_source, VERSION)
    log_user_event(session_id, "analysis_started", run_id=run_id,
                   event_data={"use_case": use_case, "technology": technology, "industry": industry})

    _user_inputs = {"use_case": use_case, "technology": technology, "industry": industry}

    try:
        result = _run_pipeline(use_case, technology, industry, run_id, session_id, VERSION)

        try:
            report_path = save_report(result, version=VERSION, run_id=run_id)
            append_test_log(result, version=VERSION, report_path=report_path, run_id=run_id)
        except Exception as save_err:
            log_error(save_err, session_id=session_id, run_id=run_id,
                      pipeline_step="save_report", user_inputs=_user_inputs,
                      app_version=VERSION)
            report_path = None

        # Build the FULL report markdown (includes the Sources section) once, up front,
        # so both Supabase and the download button get the complete report — not just the
        # analysis text. Falls back to the analysis if the local file save failed.
        if report_path:
            with open(report_path, "r", encoding="utf-8") as f:
                report_md = f.read()
        else:
            # Local save failed — rebuild enough of the report by hand. The disclaimer is
            # re-attached explicitly: no copy of a report leaves here without it.
            report_md = result.get("analysis", "") + f"\n\n---\n\n{REPORT_DISCLAIMER}\n"

        if run_id:
            complete_run(run_id, result["timing"])
            update_run_research_quality(
                run_id,
                len(result.get("sources", [])),
                result.get("research_limited", False),
                result.get("num_failed_queries", 0),
            )
            if report_path:
                save_report_to_db(run_id, report_md, result["search_queries"],
                                  os.path.basename(report_path))
            log_user_event(session_id, "report_viewed", run_id=run_id)

        st.session_state.result = result
        st.session_state.report_path = report_path
        st.session_state.current_run_id = run_id
        st.session_state.report_md = report_md

    except EmptyResearchError as research_err:
        # #29 — research came back empty; we deliberately did NOT fabricate a report
        log_error(research_err, session_id=session_id, run_id=run_id,
                  pipeline_step="research", user_inputs=_user_inputs,
                  app_version=VERSION)
        if run_id:
            mark_run_failed(run_id, research_err)

        st.warning(
            "The agent couldn't gather regulatory research just now — this is usually a "
            "temporary web-search hiccup. Please try again in a moment."
        )
        st.caption(f"Reference: `{run_id or 'no-run-id'}`")
        log_user_event(session_id, "research_failed", run_id=run_id)

    except Exception as pipeline_err:
        log_error(pipeline_err, session_id=session_id, run_id=run_id,
                  pipeline_step="pipeline", user_inputs=_user_inputs,
                  app_version=VERSION)
        if run_id:
            mark_run_failed(run_id, pipeline_err)

        st.error(
            "Something went wrong during the analysis. The error has been logged "
            "and will be investigated. Please try again — transient issues often "
            "resolve on retry."
        )
        st.caption(f"Error reference: `{run_id or 'no-run-id'}`")
        log_user_event(session_id, "pipeline_error", run_id=run_id,
                       event_data={"error_type": type(pipeline_err).__name__,
                                   "error_message": str(pipeline_err)[:500]})


# ── Display results ───────────────────────────────────────────────────────────
result = st.session_state.result
if result:
    timing = result["timing"]

    st.markdown(
        f"""
        <div class="metric-row">
            <div class="metric-card">
                <div class="label">Total time</div>
                <div class="value">{timing['total_sec']}s</div>
            </div>
            <div class="metric-card">
                <div class="label">Planning</div>
                <div class="value">{timing['planning_sec']}s</div>
            </div>
            <div class="metric-card">
                <div class="label">Research</div>
                <div class="value">{timing['research_sec']}s</div>
            </div>
            <div class="metric-card">
                <div class="label">Analysis</div>
                <div class="value">{timing['analysis_sec']}s</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if result.get("research_limited"):
        st.warning(
            "This report was generated from limited research data — some searches returned "
            "few results. Coverage may be incomplete; consider re-running for a fuller analysis."
        )

    tab_report, tab_sources, tab_queries = st.tabs(
        ["📄 Report", "🔗 Sources", "🔍 Search Queries"]
    )

    with tab_report:
        st.markdown(result["analysis"])
        st.divider()
        st.caption(REPORT_DISCLAIMER)

    with tab_sources:
        sources = result.get("sources", [])
        if sources:
            st.caption("Regulatory and policy sources the agent reviewed for this report.")
            for i, s in enumerate(sources, 1):
                title = s.get("title") or s.get("url") or "Untitled source"
                url = s.get("url", "")
                st.markdown(f"{i}. [{title}]({url})" if url else f"{i}. {title}")
        else:
            st.caption("No sources were captured for this report.")

    with tab_queries:
        for i, q in enumerate(result["search_queries"], 1):
            st.markdown(f"**{i}.** {q}")

    st.divider()

    col_dl, col_path = st.columns([1, 3])
    with col_dl:
        dl_filename = (os.path.basename(st.session_state.report_path)
                       if st.session_state.report_path else "compliance_report.md")
        downloaded = st.download_button(
            "⬇️ Download Report (.md)",
            data=st.session_state.report_md,
            file_name=dl_filename,
            mime="text/markdown",
        )
        if downloaded:
            log_user_event(
                st.session_state.supabase_session_id,
                "report_downloaded",
                run_id=st.session_state.get("current_run_id"),
                event_data={"filename": dl_filename},
            )
    with col_path:
        if not st.session_state.report_path:
            st.caption("⚠️ Local save failed — report available via download only")

    # ── Feedback (#31) ────────────────────────────────────────────────────────
    st.divider()
    run_id_for_fb = st.session_state.get("current_run_id")
    if st.session_state.get("feedback_given"):
        st.caption("✅ Thanks for your feedback — it helps improve the agent.")
    else:
        st.markdown("**Was this report helpful?**")
        fb_yes, fb_no, _ = st.columns([1, 1, 6])
        with fb_yes:
            if st.button("👍 Yes", use_container_width=True):
                log_user_event(st.session_state.supabase_session_id, "feedback",
                               run_id=run_id_for_fb, event_data={"rating": "up"})
                st.session_state.feedback_given = True
                st.rerun()
        with fb_no:
            if st.button("👎 No", use_container_width=True):
                log_user_event(st.session_state.supabase_session_id, "feedback",
                               run_id=run_id_for_fb, event_data={"rating": "down"})
                st.session_state.feedback_given = True
                st.rerun()

elif not run_btn:
    st.info(
        "Configure your analysis in the sidebar and click **Run Analysis** to start.",
        icon="👈",
    )
