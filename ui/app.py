"""Streamlit workspace for exploring payment code and grounded answers."""
from __future__ import annotations

import os
from html import escape
from pathlib import Path

import requests
import streamlit as st

from ui.api_client import (
    UIAuthenticationError,
    describe_query_error,
    QUERY_READ_TIMEOUT,
    fetch_source,
    is_local_development_mode,
    query_api,
    retrieve_api,
)

st.set_page_config(page_title="CodeGraph | Fintech workspace", page_icon="🔎",
                   layout="wide", initial_sidebar_state="expanded")
DEFAULT_API_URL = os.getenv("CODEGRAPH_API_URL", "http://127.0.0.1:8000")
PUBLIC_DEMO = os.getenv("CODEGRAPH_PUBLIC_DEMO", "0").lower() in {"1", "true", "yes"}
EXAMPLES = {
    "JazzCash callback": "Why does the JazzCash payment callback handler throw a timeout error during peak traffic?",
    "Webhook verification": "Which function verifies the JazzCash webhook signature?",
    "1LINK latency": "What is the expected 1LINK latency during peak traffic?",
}


def clear_results():
    """Remove results and authorized source content when the investigation changes."""
    st.session_state.pop("last_result", None)
    st.session_state.pop("last_query", None)
    for key in list(st.session_state):
        if key.startswith("source-"):
            del st.session_state[key]


def choose_example(label):
    st.session_state["query_text"] = EXAMPLES[label]
    st.session_state["stack_trace_text"] = ""
    clear_results()


def status_badge(status):
    return {
        "SUPPORTED": "🟢 SUPPORTED",
        "PARTIALLY_SUPPORTED": "🟡 PARTIALLY SUPPORTED",
        "CONFLICTING_EVIDENCE": "🟠 CONFLICTING EVIDENCE",
        "INSUFFICIENT_EVIDENCE": "🔴 INSUFFICIENT EVIDENCE",
    }.get(status, f"⚪ {status}")


def format_symbol(doc_id):
    return str(doc_id).replace("\\", "/").strip()


def html(markup):
    st.markdown(markup, unsafe_allow_html=True)


html("<style>" + Path(__file__).with_name("styles.css").read_text(encoding="utf-8") + "</style>")

with st.sidebar:
    html('<div class="cg-brand"><div class="cg-mark">&gt;_</div><div>'
         '<strong>CodeGraph</strong><small>Fintech workspace</small></div></div>')
    html('<div class="cg-eyebrow">Access &amp; workspace</div>')
    role = st.selectbox("Access Role", ["Junior Dev", "Senior Dev", "Security Lead"],
                        help="Choose the permissions used to retrieve and open sample code.")
    st.caption("Role-based access to the sample codebase.")
    with st.expander("Connection settings", expanded=False):
        if PUBLIC_DEMO:
            # The public target is server-owned: visitors cannot choose where role tokens go.
            api_url = DEFAULT_API_URL
            st.caption("Connected to the project API")
        else:
            api_url = st.text_input("FastAPI URL", value=DEFAULT_API_URL,
                                    help="Address of the running project API.")
        if is_local_development_mode(api_url):
            st.caption("Local development access. Authenticated deployments use server-side role credentials.")

    health_scope = api_url.rstrip("/")
    if st.session_state.get("health_scope") != health_scope:
        st.session_state["health_scope"] = health_scope
        st.session_state.pop("api_health", None)
    if st.button("Check API Health", use_container_width=True):
        try:
            response = requests.get(f"{health_scope}/health", timeout=10)
            response.raise_for_status()
            health_data = response.json()
            st.session_state["api_health"] = "healthy" if isinstance(health_data, dict) and health_data.get("status") == "healthy" else "unavailable"
        except (requests.RequestException, ValueError):
            st.session_state["api_health"] = "unavailable"
    health = st.session_state.get("api_health", "unchecked")
    health_label = {"healthy": "API responded healthy", "unavailable": "API unavailable or not healthy",
                    "unchecked": "API connection not checked"}[health]
    html(f'<div class="cg-state"><span class="cg-dot {health}"></span>{health_label}</div>')
    st.caption("Last manual check · not a live monitor")
    st.divider()
    html('<div class="cg-sidebar-note"><b>Evidence before conclusions</b>'
         '<p>Explore the code, follow the path, then open the source to verify.</p></div>')
    st.caption("Project 10 · Synthetic payment code")

html('<header class="cg-page-header"><div><div class="cg-eyebrow">WORKSPACE / PAYMENT INTEGRATIONS</div>'
     '<h1>Code intelligence workspace</h1><p>Find the code. Follow the flow. Verify the evidence.</p></div>'
     f'<span class="cg-workspace-tag">{escape(role)}</span></header>')

editor, starters = st.columns([2.15, 1], gap="large")
with editor:
    with st.container(border=True):
        html('<div class="cg-panel-heading"><span class="cg-section-number">01</span>'
             '<div><h2>Start an investigation</h2><p>A function, payment flow, or error.</p></div></div>')
        mode = st.radio("Mode", ["Explore code", "Generate answer"], horizontal=True, label_visibility="collapsed")
        exploring = mode == "Explore code"
        result_scope = (api_url.rstrip("/"), role, mode)
        if st.session_state.get("result_scope") != result_scope:
            clear_results()
            st.session_state["result_scope"] = result_scope
        if "query_text" not in st.session_state:
            st.session_state["query_text"] = EXAMPLES["JazzCash callback"]
        query = st.text_area("Question", key="query_text", height=120, max_chars=2000,
                             placeholder="Ask about a function, payment flow, or error...", on_change=clear_results)
        with st.expander("Add a stack trace (optional)"):
            stack_trace = st.text_area("Stack trace (optional)", key="stack_trace_text", height=150,
                                       max_chars=8000, placeholder="Paste an error trace to narrow the search...",
                                       on_change=clear_results)
        analyze = st.button("🔍 Explore code" if exploring else "🚀 Generate answer",
                            type="primary", use_container_width=True)
        st.caption("Code search only · no answer generation" if exploring else
                   "Evidence-based answer · local generation may take longer")
with starters:
    with st.container(border=True):
        html('<div class="cg-eyebrow">STARTER INVESTIGATIONS</div>')
        descriptions = {
            "JazzCash callback": ("JC", "Debug a payment timeout", "Trace the callback during peak traffic."),
            "Webhook verification": ("WH", "Inspect signature verification", "Locate the webhook security check."),
            "1LINK latency": ("1L", "Explore network latency", "Find the expected peak-traffic delay."),
        }
        for label, (icon, title, description) in descriptions.items():
            html(f'<div class="cg-starter"><span class="cg-starter-icon">{icon}</span>'
                 f'<div><b>{title}</b><p>{description}</p></div></div>')
            st.button(label, on_click=choose_example, args=(label,), use_container_width=True)
    html('<div class="cg-provider-strip"><span>DEMO CODEBASE</span>'
         '<b>JazzCash <i>·</i> 1LINK <i>·</i> EasyPaisa</b></div>')

if analyze:
    clear_results()
    if len(query.strip()) < 3:
        st.error("Please enter a question with at least 3 characters.")
        st.stop()
    with st.spinner("Finding relevant code and call paths..." if exploring else
                    "Gathering evidence and generating an answer; please wait. "
                    f"Response wait: {QUERY_READ_TIMEOUT:.0f} seconds."):
        try:
            request_code = retrieve_api if exploring else query_api
            data = request_code(api_url=api_url, query=query.strip(), role=role,
                                stack_trace=stack_trace.strip() or None)
            st.session_state["last_result"] = data
            st.session_state["last_query"] = query.strip()
        except (UIAuthenticationError, requests.RequestException) as exc:
            if exploring and isinstance(exc, requests.HTTPError) and exc.response is not None and exc.response.status_code == 404:
                severity, message = "error", "Explore code is unavailable on this API. Update the backend to enable it."
            else:
                severity, message = describe_query_error(exc)
            (st.warning if severity == "warning" else st.error)(message)
        except ValueError:
            st.error("The API returned an invalid response. Check the API service and try again.")

result = st.session_state.get("last_result")
if result:
    st.write("")
    html('<div class="cg-eyebrow">Investigation results</div>')
    st.subheader("Code evidence" if exploring else "Analysis Result")
    st.caption(f"Question: {st.session_state.get('last_query', query)}")
    call_path = result.get("call_path") or []
    retrieved_items = result.get("retrieved_items") or []
    citations = result.get("sources" if exploring else "citations") or []
    if exploring:
        cols = st.columns(3)
        cols[0].metric("Retrieval latency", f"{result.get('latency_ms', 0):.1f} ms")
        cols[1].metric("Code matches", len(retrieved_items))
        cols[2].metric("Call paths", 1 if call_path else 0)
        st.caption(f"Access role: {result.get('role', role)} · Retrieved evidence to inspect; no answer generated.")
    else:
        with st.container(border=True):
            status = result.get("status", "UNKNOWN")
            severity = {"SUPPORTED": st.success, "PARTIALLY_SUPPORTED": st.warning,
                        "CONFLICTING_EVIDENCE": st.warning, "INSUFFICIENT_EVIDENCE": st.error}.get(status, st.info)
            severity(status_badge(status))
            st.markdown("### Answer")
            st.write(result.get("answer", ""))
            st.caption(f"{result.get('role', role)} · {result.get('provider', 'N/A')} / {result.get('model', 'N/A')}")
        with st.expander("📊 Query Telemetry"):
            if result.get("trace_id"):
                st.caption(f"Trace ID: {result['trace_id']}")
            cols = st.columns(5)
            cols[0].metric("Latency", f"{result.get('latency_ms', 0):.1f} ms")
            cols[1].metric("Prompt Tokens", result.get("prompt_tokens", 0))
            cols[2].metric("Completion Tokens", result.get("completion_tokens", 0))
            cols[3].metric("Total Tokens", result.get("total_tokens", 0))
            cols[4].metric("Cost", f"${result.get('cost_usd', 0):.6f}")

    source_tab, path_tab, chunk_tab = st.tabs([f"Sources · {len(citations)}", "Call path", f"Code matches · {len(retrieved_items)}"])
    with source_tab:
        st.markdown("### Source references" if exploring else "### Citations")
        st.caption("Open a reference to inspect the source with your selected role.")
        for index, citation in enumerate(citations, start=1):
            with st.container(border=True):
                if not isinstance(citation, dict):
                    st.write(f"[{index}] {citation}")
                    continue
                file_path = citation.get("file_path", citation.get("path", "Unknown file"))
                symbol = citation.get("symbol_name", citation.get("symbol", "Unknown symbol"))
                start_line = citation.get("start_line", citation.get("line_start"))
                end_line = citation.get("end_line", citation.get("line_end"))
                html(f'<div class="cg-reference"><span class="cg-path-number">{index:02}</span>'
                     f'<strong>{escape(str(symbol))}</strong></div>')
                st.code(str(file_path), language="text")
                details = []
                if start_line is not None:
                    details.append(f"Lines {start_line}–{end_line}" if end_line is not None else f"Line {start_line}")
                if citation.get("source"):
                    details.append(f"Retrieved via {citation['source']}")
                if details:
                    st.caption(" · ".join(details))
                if start_line is not None:
                    source_key = f"source-{index}-{file_path}-{start_line}"
                    if st.button("Open source", key=f"open-{source_key}", icon=":material/open_in_new:"):
                        try:
                            st.session_state[source_key] = fetch_source(api_url, str(file_path), role)
                        except (UIAuthenticationError, requests.RequestException, ValueError):
                            st.error("Could not open source. Check your access role and API connection.")
                    if st.session_state.get(source_key) is not None:
                        st.code(st.session_state[source_key], language="python", line_numbers=True)
                if citation.get("text"):
                    st.caption(str(citation["text"]))
        if not citations:
            st.info("No source matches were returned." if exploring else "No citations were returned. Inspect code with Explore before drawing conclusions.")
    with path_tab:
        st.markdown("### Execution / Call Path")
        st.caption("Sequence returned by retrieval; inspect the source to verify each step.")
        for index, node in enumerate(call_path, start=1):
            html(f'<div class="cg-path"><span class="cg-path-number">{index:02}</span>'
                 f'<code>{escape(format_symbol(node))}</code></div>')
        if not call_path:
            st.caption("No execution call path was returned.")
    with chunk_tab:
        with st.expander(f"🔍 Retrieved Code Chunks ({len(retrieved_items)})", expanded=True):
            for index, item in enumerate(retrieved_items, start=1):
                if not isinstance(item, dict):
                    st.write(item)
                    continue
                st.caption(f"Match {index:02} · {item.get('source', 'retrieval')}")
                st.code(format_symbol(item.get("doc_id", item.get("file_path", "Unknown"))), language="text")
                symbol = item.get("symbol_name", item.get("symbol", ""))
                if symbol:
                    st.caption(f"Symbol: {symbol}")
                st.divider()
            if not retrieved_items:
                st.caption("No retrieved items were returned.")
else:
    html('<section class="cg-empty"><span class="cg-empty-icon">&lt;/&gt;</span><div>'
         '<h3>Your evidence will appear here</h3><p>Run an investigation to see source references, the call path, and code matches.</p>'
         '</div><span class="cg-empty-tag">READY FOR A QUESTION</span></section>')
html('<div class="cg-footer"><span>CodeGraph RAG · Project 10</span><span>Synthetic code · Verify evidence before relying on an answer</span></div>')
