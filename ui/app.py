"""Streamlit UI for the CodeGraph RAG system."""

from __future__ import annotations

import os
from html import escape

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


# ---------------------------------------------------------------------------
# Page configuration
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="CodeGraph RAG",
    page_icon="🔎",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_API_URL = os.getenv("CODEGRAPH_API_URL", "http://127.0.0.1:8000")
PUBLIC_DEMO = os.getenv("CODEGRAPH_PUBLIC_DEMO", "0").lower() in {"1", "true", "yes"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def status_badge(status: str) -> str:
    """Return a visual label for the answer status."""
    labels = {
        "SUPPORTED": "🟢 SUPPORTED",
        "PARTIALLY_SUPPORTED": "🟡 PARTIALLY SUPPORTED",
        "CONFLICTING_EVIDENCE": "🟠 CONFLICTING EVIDENCE",
        "INSUFFICIENT_EVIDENCE": "🔴 INSUFFICIENT EVIDENCE",
    }
    return labels.get(status, f"⚪ {status}")


def format_symbol(doc_id: str) -> str:
    """Format an internal document ID for display."""
    return doc_id.replace("\\", "/").strip()


# ---------------------------------------------------------------------------
# Styling
# ---------------------------------------------------------------------------

st.markdown(
    """
    <style>
    .main-title {
        font-size: 2.2rem;
        font-weight: 700;
        margin-bottom: 0.2rem;
    }

    .subtitle {
        color: #64748b;
        margin-bottom: 1.5rem;
    }

    .metric-card {
        padding: 1rem;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        background: #f8fafc;
    }

    .citation-card {
        padding: 0.9rem;
        margin-bottom: 0.7rem;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        background: #ffffff;
    }

    .path-node {
        font-family: monospace;
        font-size: 0.9rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

st.markdown(
    '<div class="main-title">🔎 CodeGraph RAG</div>',
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="subtitle">'
    "Cursor-style Codebase Graph Retrieval &amp; Grounded Analysis"
    "</div>",
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("⚙️ Configuration")

    if PUBLIC_DEMO:
        # A visitor-controlled URL would send server-side role credentials to
        # an arbitrary host. In public demos the target comes ONLY from env.
        api_url = DEFAULT_API_URL
        st.caption("Connected to the project API")
    else:
        api_url = st.text_input(
            "FastAPI URL",
            value=DEFAULT_API_URL,
            help="URL of the running CodeGraph RAG FastAPI service.",
        )

    role = st.selectbox(
        "Access Role",
        [
            "Junior Dev",
            "Senior Dev",
            "Security Lead",
        ],
        index=0,
        help="Controls RBAC filtering during retrieval.",
    )

    if is_local_development_mode(api_url):
        st.info(
            "Local development mode: loopback API access uses the API's "
            "development role selector. Configure API_ROLE_TOKENS for authenticated access."
        )

    st.divider()

    st.subheader("System")

    health_placeholder = st.empty()

    if st.button("Check API Health", use_container_width=True):
        try:
            response = requests.get(
                f"{api_url.rstrip('/')}/health",
                timeout=10,
            )
            response.raise_for_status()

            health_data = response.json()

            health_placeholder.success(
                f"API healthy: {health_data}"
            )

        except requests.RequestException as exc:
            health_placeholder.error(
                f"API unavailable: {exc}"
            )

    st.divider()

    st.caption(
        "CodeGraph RAG uses hybrid retrieval, reranking, "
        "RBAC-aware graph expansion, and grounded answer generation."
    )


# ---------------------------------------------------------------------------
# Query input
# ---------------------------------------------------------------------------

st.subheader("Ask about the codebase")

mode = st.radio("Mode", ["Explore code", "Generate answer"], horizontal=True)
exploring = mode == "Explore code"
if exploring:
    st.caption("Find relevant code and call paths, then open the source. No answer generation.")

# Keep source and result state within the API, role and mode that produced it.
result_scope = (api_url.rstrip("/"), role, mode)
if st.session_state.get("result_scope") != result_scope:
    st.session_state.pop("last_result", None)
    for key in list(st.session_state):
        if key.startswith("source-"):
            del st.session_state[key]
    st.session_state["result_scope"] = result_scope

query = st.text_area(
    "Question",
    value=(
        "Why does the JazzCash payment callback handler "
        "throw a timeout error during peak traffic?"
    ),
    height=110,
    max_chars=2000,
    placeholder="Ask a question about the codebase...",
)

stack_trace = st.text_area(
    "Stack trace (optional)",
    value="",
    height=150,
    max_chars=8000,
    placeholder="Paste a stack trace here if you have one...",
)

analyze = st.button(
    "🔍 Explore code" if exploring else "🚀 Generate answer",
    type="primary",
    use_container_width=True,
)


# ---------------------------------------------------------------------------
# Query execution
# ---------------------------------------------------------------------------

if analyze:
    if len(query.strip()) < 3:
        st.error("Please enter a question with at least 3 characters.")
        st.stop()

    st.session_state.pop("last_result", None)
    for key in list(st.session_state):
        if key.startswith("source-"):
            del st.session_state[key]
    with st.spinner(
        "Finding relevant code and call paths..." if exploring else
        "Gathering code evidence and generating an answer; please wait. "
        f"Configured response wait: {QUERY_READ_TIMEOUT:.0f} seconds."
    ):
        try:
            request_code = retrieve_api if exploring else query_api
            data = request_code(
                api_url=api_url,
                query=query.strip(),
                role=role,
                stack_trace=stack_trace.strip() or None,
            )

            st.session_state["last_result"] = data

        except (UIAuthenticationError, requests.RequestException) as exc:
            if exploring and isinstance(exc, requests.HTTPError) and exc.response is not None and exc.response.status_code == 404:
                severity, message = "error", "Explore code is unavailable on this API. Update the backend to enable it."
            else:
                severity, message = describe_query_error(exc)
            if severity == "warning":
                st.warning(message)
            else:
                st.error(message)

        except ValueError as exc:
            st.error(f"Invalid JSON response from API: {exc}")


# ---------------------------------------------------------------------------
# Result rendering
# ---------------------------------------------------------------------------

result = st.session_state.get("last_result")

if result:
    st.divider()

    if exploring:
        st.subheader("Code evidence")
        st.caption("Retrieved matches and paths are evidence to inspect; no answer was generated.")
        cols = st.columns(3)
        cols[0].metric("Retrieval latency", f"{result.get('latency_ms', 0):.1f} ms")
        cols[1].metric("Code matches", len(result.get("retrieved_items", [])))
        cols[2].metric("Call paths", len(result.get("call_path", [])))
        st.caption(f"Access role: {result.get('role', role)}")
    else:
        st.subheader("Analysis Result")

        status = result.get("status", "UNKNOWN")

        col1, col2 = st.columns([3, 1])

        with col1:
            st.markdown("### Answer")
            st.write(result.get("answer", ""))

        with col2:
            st.markdown("### Status")
            st.info(status_badge(status))

            st.markdown("**Role**")
            st.write(result.get("role", role))

            st.markdown("**Provider**")
            st.write(result.get("provider", "N/A"))

            st.markdown("**Model**")
            st.write(result.get("model", "N/A"))

        # -----------------------------------------------------------------------
        # Telemetry
        # -----------------------------------------------------------------------

        st.markdown("### 📊 Query Telemetry")
        if result.get("trace_id"):
            st.caption(f"Trace ID: {result['trace_id']}")

        metric_cols = st.columns(5)

        with metric_cols[0]:
            st.metric(
                "Latency",
                f"{result.get('latency_ms', 0):.1f} ms",
            )

        with metric_cols[1]:
            st.metric(
                "Prompt Tokens",
                result.get("prompt_tokens", 0),
            )

        with metric_cols[2]:
            st.metric(
                "Completion Tokens",
                result.get("completion_tokens", 0),
            )

        with metric_cols[3]:
            st.metric(
                "Total Tokens",
                result.get("total_tokens", 0),
            )

        with metric_cols[4]:
            st.metric(
                "Cost",
                f"${result.get('cost_usd', 0):.6f}",
            )

    # -----------------------------------------------------------------------
    # Call path
    # -----------------------------------------------------------------------

    call_path = result.get("call_path") or []

    st.markdown("### 🔗 Execution / Call Path")

    if call_path:
        for index, node in enumerate(call_path, start=1):
            st.markdown(
                f'<div class="path-node">'
                f"<b>{index}.</b> {escape(format_symbol(node))}"
                f"</div>",
                unsafe_allow_html=True,
            )

            if index < len(call_path):
                st.markdown("↓")
    else:
        st.caption("No execution call path was returned.")

    # -----------------------------------------------------------------------
    # Citations
    # -----------------------------------------------------------------------

    citations = result.get("sources" if exploring else "citations") or []

    st.markdown("### 📚 Source references" if exploring else "### 📚 Citations")

    if citations:
        for index, citation in enumerate(citations, start=1):
            if isinstance(citation, dict):
                file_path = citation.get(
                    "file_path",
                    citation.get("path", "Unknown file"),
                )

                symbol = citation.get(
                    "symbol_name",
                    citation.get("symbol", "Unknown symbol"),
                )

                start_line = citation.get(
                    "start_line",
                    citation.get("line_start"),
                )

                end_line = citation.get(
                    "end_line",
                    citation.get("line_end"),
                )

                with st.container(border=True):
                    st.markdown(f"**[{index}] {symbol}**")
                    st.code(str(file_path), language="text")
                    if citation.get("source"):
                        st.caption(f"Retrieved via {citation['source']}")

                    if start_line is not None:
                        if end_line is not None:
                            st.caption(
                                f"Lines {start_line}–{end_line}"
                            )
                        else:
                            st.caption(f"Line {start_line}")

                        source_key = f"source-{index}-{file_path}-{start_line}"
                        if st.button(
                            "Open source",
                            key=f"open-{source_key}",
                            icon=":material/open_in_new:",
                        ):
                            try:
                                st.session_state[source_key] = fetch_source(
                                    api_url,
                                    str(file_path),
                                    role,
                                )
                            except (UIAuthenticationError, requests.RequestException, ValueError) as exc:
                                st.error(f"Could not open source: {exc}")

                        if st.session_state.get(source_key) is not None:
                            st.code(
                                st.session_state[source_key],
                                language="python",
                                line_numbers=True,
                            )

                    if citation.get("text"):
                        st.caption(str(citation["text"]))

            else:
                with st.container(border=True):
                    st.write(f"[{index}] {citation}")

    else:
        st.caption("No source matches were returned." if exploring else "No citations were returned.")

    # -----------------------------------------------------------------------
    # Retrieved items
    # -----------------------------------------------------------------------

    retrieved_items = result.get("retrieved_items") or []

    with st.expander(
        f"🔍 Retrieved Code Chunks ({len(retrieved_items)})"
    ):
        if retrieved_items:
            for index, item in enumerate(
                retrieved_items,
                start=1,
            ):
                if not isinstance(item, dict):
                    st.write(item)
                    continue

                st.markdown(f"**{index}.**")

                doc_id = item.get(
                    "doc_id",
                    item.get("file_path", "Unknown"),
                )

                symbol = item.get(
                    "symbol_name",
                    item.get("symbol", ""),
                )

                source = item.get(
                    "source",
                    "retrieval",
                )

                col_a, col_b = st.columns([4, 1])

                with col_a:
                    st.code(
                        format_symbol(str(doc_id)),
                        language="text",
                    )

                    if symbol:
                        st.caption(
                            f"Symbol: {symbol}"
                        )

                with col_b:
                    st.caption(
                        f"Source: {source}"
                    )

                st.divider()
        else:
            st.caption("No retrieved items were returned.")