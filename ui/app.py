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
    st.caption("Demo roles illustrate access to synthetic payment code.")
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
    st.caption("Status reflects the last manual check.")
    st.divider()
    html('<div class="cg-eyebrow">How it works</div>')
    st.markdown("**01 · Explore**  \nFind relevant symbols and code.")
    st.markdown("**02 · Follow the path**  \nInspect the returned call sequence.")
    st.markdown("**03 · Verify**  \nOpen source before drawing conclusions.")
    st.divider()
    st.caption("JazzCash · 1LINK · EasyPaisa\n\nSynthetic integration examples")

html('<section class="cg-hero"><div class="cg-eyebrow">PROJECT 10 / CODE INTELLIGENCE</div>'
     '<h1>Understand your<br>payment code.</h1>'
     '<p>Explore relevant code, follow call paths, and inspect the source behind every answer.</p>'
     '<div class="cg-pills"><span class="cg-pill">Hybrid code search</span>'
     '<span class="cg-pill">Graph exploration</span>'
     f'<span class="cg-pill">{escape(role)}</span></div></section>')

with st.container(border=True):
    html('<div class="cg-eyebrow">Investigation</div>')
    st.subheader("Ask about the codebase")
    mode = st.radio("Mode", ["Explore code", "Generate answer"], horizontal=True)
    exploring = mode == "Explore code"
    if exploring:
        st.caption("Find code and call paths without waiting for an AI-generated answer.")
    else:
        st.caption("Generate an answer from retrieved evidence. The local model may take longer to respond.")
    result_scope = (api_url.rstrip("/"), role, mode)
    if st.session_state.get("result_scope") != result_scope:
        clear_results()
        st.session_state["result_scope"] = result_scope
    st.caption("Try a sample question")
    for column, label in zip(st.columns(3), EXAMPLES):
        column.button(label, on_click=choose_example, args=(label,), use_container_width=True)
    if "query_text" not in st.session_state:
        st.session_state["query_text"] = EXAMPLES["JazzCash callback"]
    query = st.text_area("Question", key="query_text", height=110, max_chars=2000,
                         placeholder="Ask about a function, payment flow, or error...", on_change=clear_results)
    with st.expander("Add a stack trace (optional)"):
        stack_trace = st.text_area("Stack trace (optional)", key="stack_trace_text", height=150,
                                   max_chars=8000, placeholder="Paste an error trace to narrow the search...",
                                   on_change=clear_results)
    analyze = st.button("🔍 Explore code" if exploring else "🚀 Generate answer",
                        type="primary", use_container_width=True)

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
    html('<section class="cg-empty"><h3>Your investigation starts here.</h3>'
         '<p>Choose a sample question or ask your own. Explore first, then generate an answer when you need one.</p>'
         '<div class="cg-steps"><div class="cg-step"><b>01 / Find the code</b><span>Search symbols and related snippets.</span></div>'
         '<div class="cg-step"><b>02 / Follow the flow</b><span>Inspect the returned call sequence.</span></div>'
         '<div class="cg-step"><b>03 / Check the source</b><span>Verify the evidence behind the result.</span></div></div></section>')
html('<div class="cg-footer">CodeGraph RAG · Project 10 · Synthetic Pakistani payment integrations</div>')
