"""POST /query, GET /health, GET /metrics route handlers."""

from __future__ import annotations

import logging
import re
import time

import httpx
import uuid
from html import escape
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import HTMLResponse
from starlette.concurrency import run_in_threadpool

from src.api.dependencies import (
    app_state,
    bind_requested_role,
    get_authenticated_role,
    get_generator,
    get_indexer,
    get_retriever,
)
from src.api.models import (
    AnswerStatus,
    CitationItem,
    ErrorResponse,
    HealthResponse,
    MetricsResponse,
    QueryRequest,
    QueryResponse,
    RetrievedItem,
    RetrievalResponse,
)
from src.config import settings
from src.generation.generator import CodeRAGGenerator
from src.ingestion.chunker import SymbolChunker
from src.security.rbac import rbac_manager
from src.retrieval.hybrid import HybridRetriever
from src.telemetry import (
    QueryRecord,
    build_query_cache_key,
    create_query_trace,
    estimate_cost,
    metrics_store,
    query_result_cache,
    trace_store,
)

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/retrieve", response_model=RetrievalResponse)
async def retrieve_code(
    req: QueryRequest,
    authenticated_role: str | None = Depends(get_authenticated_role),
    retriever: HybridRetriever = Depends(get_retriever),
) -> RetrievalResponse:
    """Retrieve role-authorized source references and paths without an LLM call."""
    requested_role = req.role if "role" in req.model_fields_set else None
    role = bind_requested_role(requested_role, authenticated_role)
    effective_query = req.query
    if req.stack_trace:
        effective_query += f"\n\nStack trace provided by user:\n```\n{req.stack_trace}\n```"
    started = time.perf_counter()
    try:
        result = await run_in_threadpool(retriever.retrieve, effective_query, role=role)
        # Defense in depth before exposing filenames or symbol names. The
        # pipeline already filters candidates and graph traversal by this role.
        clearance = rbac_manager.get_clearance_for_role(role)
        if any(not rbac_manager.is_chunk_authorized(item.chunk, role) for item in result.items):
            raise RuntimeError("Unauthorized retrieval result")
        graph = retriever.graph
        if any(
            node not in graph.nodes
            or str(graph.nodes[node].get("security_level", "")).lower() not in clearance
            for path in result.execution_paths for node in path
        ):
            raise RuntimeError("Unauthorized execution path")
        sources = [CitationItem(
            doc_id=item.chunk.doc_id,
            symbol_name=item.chunk.symbol_name,
            file_path=item.chunk.file_path,
            start_line=item.chunk.start_line,
            end_line=item.chunk.end_line,
            security_level=item.chunk.security_level,
            source=item.source,
        ) for item in result.items]
        return RetrievalResponse(
            query=req.query, role=role, sources=sources,
            retrieved_items=_build_retrieved_items(result),
            call_path=_format_call_paths(result, graph),
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
        )
    except Exception as exc:
        # Do not expose source content or provider secrets from exception text.
        raise HTTPException(status_code=500, detail="Code retrieval failed.") from exc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _estimate_answer_cost(answer) -> float:
    if answer.provider == "groq" and answer.model == "openai/gpt-oss-120b":
        # Groq published list prices checked 2026-10-11. Estimate, not an invoice.
        return round((answer.prompt_tokens * 0.15 + answer.completion_tokens * 0.60) / 1_000_000, 8)
    return estimate_cost(answer.model, answer.total_tokens)


def _classify_status(answer: str, n_citations: int, n_items: int) -> AnswerStatus:
    """Heuristic answer-confidence classifier.

    Rules (applied in order):
    - No items retrieved -> INSUFFICIENT_EVIDENCE
    - Conservative fallback -> INSUFFICIENT_EVIDENCE
    - Validated explicit status with citations -> that status
    - Answer contains explicit contradiction language -> CONFLICTING_EVIDENCE
    - 2+ grounded citations -> SUPPORTED
    - 1 grounded citation -> PARTIALLY_SUPPORTED
    - Answer contains hedging language -> INSUFFICIENT_EVIDENCE
    - Default -> PARTIALLY_SUPPORTED
    """
    if n_items == 0:
        return AnswerStatus.INSUFFICIENT_EVIDENCE

    answer_lower = answer.lower()

    conflict_markers = [
        "contradicts",
        "contradiction",
        "conflicting evidence",
        "inconsistent evidence",
        "on the other hand",
    ]

    hedge_markers = [
        "may",
        "might",
        "possibly",
        "unclear",
        "not certain",
        "insufficient",
        "cannot determine",
        "no direct",
        "limited information",
    ]

    if answer.lstrip().startswith("## Evidence-based assessment"):
        return AnswerStatus.INSUFFICIENT_EVIDENCE

    # One source can fully establish a single documented fact. A validated
    # explicit status has more meaning than counting duplicate supporting files.
    plain = answer.replace("**", "").replace("__", "")
    explicit = re.findall(
        r"(?im)^\s*(?:#{1,6}\s*)?evidence status\s*:\s*"
        r"(insufficient evidence|partially supported|supported|conflicting evidence)\s*\.?\s*$",
        plain,
    )
    if explicit and n_citations:
        labels = {
            "supported": AnswerStatus.SUPPORTED,
            "partially supported": AnswerStatus.PARTIALLY_SUPPORTED,
            "insufficient evidence": AnswerStatus.INSUFFICIENT_EVIDENCE,
            "conflicting evidence": AnswerStatus.CONFLICTING_EVIDENCE,
        }
        return labels[explicit[-1].lower()]

    if any(m in answer_lower for m in conflict_markers):
        return AnswerStatus.CONFLICTING_EVIDENCE

    if n_citations >= 2:
        return AnswerStatus.SUPPORTED

    if n_citations == 1:
        return AnswerStatus.PARTIALLY_SUPPORTED

    if any(m in answer_lower for m in hedge_markers):
        return AnswerStatus.INSUFFICIENT_EVIDENCE

    return AnswerStatus.PARTIALLY_SUPPORTED


def _build_citation_items(gen_answer, retrieval_result) -> List[CitationItem]:
    """Resolve GeneratedAnswer.citations (doc_ids) back to CitationItems."""
    item_map = {item.chunk.doc_id: item for item in retrieval_result.items}
    items: List[CitationItem] = []
    for doc_id in gen_answer.citations:
        retrieved_item = item_map.get(doc_id)
        if retrieved_item is None:
            continue
        chunk = retrieved_item.chunk
        items.append(
            CitationItem(
                doc_id=doc_id,
                symbol_name=chunk.symbol_name,
                file_path=chunk.file_path,
                start_line=chunk.start_line,
                end_line=chunk.end_line,
                security_level=chunk.security_level,
                source=retrieved_item.source,
            )
        )
    return items


def _build_retrieved_items(retrieval_result) -> List[RetrievedItem]:
    return [
        RetrievedItem(
            doc_id=item.chunk.doc_id,
            symbol_name=item.chunk.symbol_name,
            file_path=item.chunk.file_path,
            start_line=item.chunk.start_line,
            end_line=item.chunk.end_line,
            source=item.source,
            rrf_score=item.rrf_score,
            rerank_score=item.rerank_score,
            hop=item.hop,
            direction=item.direction,
        )
        for item in retrieval_result.items
    ]


def _format_call_paths(retrieval_result, graph) -> List[str]:
    """Convert raw node-id paths to human-readable symbol chains."""
    paths: List[str] = []
    for path in retrieval_result.execution_paths:
        symbols = [graph.nodes[n].get("symbol_name", n) for n in path if n in graph.nodes]
        if symbols:
            paths.append(" → ".join(symbols))
    return paths


def _record_query_metrics(
    *,
    query_id: str,
    role: str,
    latency_ms: float,
    cache_hit: bool,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    cost_usd: float,
    retrieval_ms: float = 0.0,
    generation_ms: float = 0.0,
) -> None:
    metrics_store.record(
        QueryRecord(
            query_id=query_id,
            role=role,
            latency_ms=latency_ms,
            retrieval_ms=retrieval_ms,
            generation_ms=generation_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost_usd=cost_usd,
            cache_hit=cache_hit,
        )
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post(
    "/query",
    response_model=QueryResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid request"},
        422: {"description": "Validation error"},
        503: {"model": ErrorResponse, "description": "Service not ready"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
        429: {"model": ErrorResponse, "description": "Cloud provider rate limit"},
        504: {"model": ErrorResponse, "description": "Generation wait expired"},
    },
    summary="Answer a natural-language question about the codebase",
    description=(
        "Runs the full CodeGraph RAG pipeline: "
        "RBAC-aware hybrid retrieval → RRF → cross-encoder rerank → "
        "graph expansion → LLM answer generation → citations → call paths."
    ),
)
async def query_endpoint(
    req: QueryRequest,
    generator: CodeRAGGenerator = Depends(get_generator),
    authenticated_role: str | None = Depends(get_authenticated_role),
) -> QueryResponse:
    requested_role = req.role if "role" in req.model_fields_set else None
    effective_role = bind_requested_role(requested_role, authenticated_role)
    t_start = time.perf_counter()
    query_id = str(uuid.uuid4())
    trace_id = query_id
    cache_key = build_query_cache_key(req.query, effective_role, req.stack_trace)
    cached_result = query_result_cache.get(cache_key) if cache_key else None

    if cached_result is not None:
        latency_ms = round((time.perf_counter() - t_start) * 1000, 2)
        cached_response = cached_result["response"]
        cached_trace = cached_result["trace"]
        trace_store.record(
            create_query_trace(
                trace_id=trace_id,
                raw_query=req.query,
                role=effective_role,
                **cached_trace,
                answer_status=cached_response["status"],
                latency_ms=latency_ms,
                cache_hit=True,
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
                cost_usd=0.0,
            )
        )
        _record_query_metrics(
            query_id=query_id,
            role=effective_role,
            latency_ms=latency_ms,
            cache_hit=True,
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            cost_usd=0.0,
        )
        return QueryResponse(
            trace_id=trace_id,
            query=req.query,
            role=effective_role,
            answer=cached_response["answer"],
            status=cached_response["status"],
            citations=cached_response["citations"],
            retrieved_items=cached_response["retrieved_items"],
            call_path=cached_response["call_path"],
            model=cached_response["model"],
            provider=cached_response["provider"],
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            latency_ms=latency_ms,
            cost_usd=0.0,
        )

    # Augment query with stack trace if provided
    effective_query = req.query
    if req.stack_trace:
        effective_query = (
            f"{req.query}\n\nStack trace provided by user:\n```\n{req.stack_trace}\n```"
        )

    try:
        gen_answer = await run_in_threadpool(
            generator.generate,
            effective_query,
            role=effective_role,
        )
    except httpx.TimeoutException as exc:
        logger.warning("Generation wait expired: trace_id=%s type=%s", trace_id, type(exc).__name__)
        raise HTTPException(status_code=504, detail="Generation wait expired.") from exc
    except httpx.HTTPStatusError as exc:
        # Only classify responses from the fixed, official Groq destination.
        if generator.provider == "groq" and exc.request.url.host == "api.groq.com":
            upstream_status = exc.response.status_code
            logger.warning("Groq request rejected: trace_id=%s status=%s", trace_id, upstream_status)
            if upstream_status == 429:
                raise HTTPException(status_code=429, detail="Cloud generation rate limit reached.") from exc
            if upstream_status in (401, 403):
                raise HTTPException(status_code=503, detail="Cloud generation credentials were rejected.") from exc
            raise HTTPException(status_code=502, detail="Cloud generation request failed.") from exc
        raise HTTPException(status_code=500, detail="Generation failed: HTTPStatusError") from exc
    except ValueError as exc:
        # Unknown role or validation error from RBAC
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Generation failed: {type(exc).__name__}",
        )

    retrieval_result = gen_answer.retrieval_result
    if retrieval_result is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Retrieval result missing from generator output.",
        )

    # Build structured response parts
    citation_items = _build_citation_items(gen_answer, retrieval_result)
    retrieved_items = _build_retrieved_items(retrieval_result)

    graph = generator.retriever.graph
    call_path = _format_call_paths(retrieval_result, graph)

    answer_status = _classify_status(gen_answer.answer, len(citation_items), len(retrieved_items))

    latency_ms = round((time.perf_counter() - t_start) * 1000, 2)
    cost = _estimate_answer_cost(gen_answer)

    restricted_doc_ids = {
        item.chunk.doc_id
        for item in retrieval_result.items
        if item.chunk.security_level.lower() == "restricted"
    }
    restricted_marker = "[REDACTED: restricted]"
    retrieved_chunk_trace = [
        {
            "doc_id": restricted_marker if item.chunk.doc_id in restricted_doc_ids else item.chunk.doc_id,
            "symbol_name": restricted_marker if item.chunk.doc_id in restricted_doc_ids else item.chunk.symbol_name,
            "symbol_type": item.chunk.symbol_type,
            "file_path": restricted_marker if item.chunk.doc_id in restricted_doc_ids else item.chunk.file_path,
            "start_line": None if item.chunk.doc_id in restricted_doc_ids else item.chunk.start_line,
            "end_line": None if item.chunk.doc_id in restricted_doc_ids else item.chunk.end_line,
            "security_level": item.chunk.security_level,
            "source": item.source,
        }
        for item in retrieval_result.items
    ]
    retriever_scores = [
        {
            "doc_id": restricted_marker if item.chunk.doc_id in restricted_doc_ids else item.chunk.doc_id,
            "rrf_score": item.rrf_score,
            "rerank_score": item.rerank_score,
            "source": item.source,
        }
        for item in retrieval_result.items
    ]
    trace_execution_steps = []
    for path in retrieval_result.execution_paths:
        if any(node in restricted_doc_ids for node in path):
            trace_execution_steps.append("[REDACTED: restricted execution path]")
            continue
        symbols = [graph.nodes[node].get("symbol_name", node) for node in path if node in graph.nodes]
        if symbols:
            trace_execution_steps.append(" → ".join(symbols))

    final_context = [
        {
            "doc_id": restricted_marker if item.chunk.doc_id in restricted_doc_ids else item.chunk.doc_id,
            "symbol_name": restricted_marker if item.chunk.doc_id in restricted_doc_ids else item.chunk.symbol_name,
            "file_path": restricted_marker if item.chunk.doc_id in restricted_doc_ids else item.chunk.file_path,
            "security_level": item.chunk.security_level,
            "content": (
                "[REDACTED: restricted]"
                if item.chunk.doc_id in restricted_doc_ids
                else item.chunk.content.strip()
            ),
        }
        for item in retrieval_result.items
    ]
    citation_trace = [
        {
            "doc_id": restricted_marker if item.doc_id in restricted_doc_ids else item.doc_id,
            "symbol_name": restricted_marker if item.doc_id in restricted_doc_ids else item.symbol_name,
            "file_path": restricted_marker if item.doc_id in restricted_doc_ids else item.file_path,
            "start_line": None if item.doc_id in restricted_doc_ids else item.start_line,
            "end_line": None if item.doc_id in restricted_doc_ids else item.end_line,
            "security_level": item.security_level,
            "source": item.source,
        }
        for item in citation_items
    ]
    trace_data = {
        "retrieved_chunks": retrieved_chunk_trace,
        "reranker_scores": retriever_scores,
        "graph_expansion_steps": trace_execution_steps,
        "final_context": final_context,
        "citations": citation_trace,
    }

    trace = create_query_trace(
        trace_id=trace_id,
        raw_query=req.query,
        role=effective_role,
        **trace_data,
        answer_status=answer_status.value,
        latency_ms=latency_ms,
        cache_hit=False,
        prompt_tokens=gen_answer.prompt_tokens,
        completion_tokens=gen_answer.completion_tokens,
        total_tokens=gen_answer.total_tokens,
        cost_usd=cost,
    )
    trace_store.record(trace)

    # Telemetry
    retrieval_ms = retrieval_result.timings_ms.get("total_ms", 0.0) if retrieval_result.timings_ms else 0.0
    generation_ms = gen_answer.latency_ms - retrieval_ms if gen_answer.latency_ms > retrieval_ms else gen_answer.latency_ms
    _record_query_metrics(
        query_id=query_id,
        role=effective_role,
        latency_ms=latency_ms,
        retrieval_ms=retrieval_ms,
        generation_ms=max(0.0, generation_ms),
        cache_hit=False,
        prompt_tokens=gen_answer.prompt_tokens,
        completion_tokens=gen_answer.completion_tokens,
        total_tokens=gen_answer.total_tokens,
        cost_usd=cost,
    )

    response = QueryResponse(
        trace_id=trace_id,
        query=req.query,
        role=effective_role,
        answer=gen_answer.answer,
        status=answer_status,
        citations=citation_items,
        retrieved_items=retrieved_items,
        call_path=call_path,
        model=gen_answer.model,
        provider=gen_answer.provider,
        prompt_tokens=gen_answer.prompt_tokens,
        completion_tokens=gen_answer.completion_tokens,
        total_tokens=gen_answer.total_tokens,
        latency_ms=latency_ms,
        cost_usd=cost,
    )
    if cache_key:
        query_result_cache.set(
            cache_key,
            {
                "response": {
                    "answer": response.answer,
                    "status": response.status.value,
                    "citations": [item.model_dump(mode="json") for item in response.citations],
                    "retrieved_items": [item.model_dump(mode="json") for item in response.retrieved_items],
                    "call_path": response.call_path,
                    "model": response.model,
                    "provider": response.provider,
                },
                "trace": trace_data,
            },
        )
    return response


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Service health check",
)
async def health_endpoint() -> HealthResponse:
    if not app_state.is_ready() or app_state.indexer is None:
        return HealthResponse(status="initialising", indexed=False)

    indexer = app_state.indexer
    graph = indexer.graph_builder.graph
    return HealthResponse(
        status="healthy",
        indexed=True,
        chunks=len(indexer.chunks),
        graph_nodes=graph.number_of_nodes(),
        graph_edges=graph.number_of_edges(),
    )


@router.get(
    "/metrics",
    response_model=MetricsResponse,
    summary="Runtime performance metrics",
    description=(
        "Returns rolling p50/p95 latency, token counts, cost estimates, "
        "and cache hit rate. Zero values are returned until queries have been processed."
    ),
)
async def metrics_endpoint(
    authenticated_role: str | None = Depends(get_authenticated_role),
) -> MetricsResponse:
    summary = metrics_store.summary()
    return MetricsResponse(**summary)


@router.get(
    "/source/{file_path:path}",
    response_class=HTMLResponse,
    summary="Open an authorized source file",
)
async def source_file_endpoint(
    file_path: str,
    role: str = Query(...),
    authenticated_role: str | None = Depends(get_authenticated_role),
) -> HTMLResponse:
    effective_role = bind_requested_role(role, authenticated_role)
    try:
        clearance = rbac_manager.get_clearance_for_role(effective_role)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    sample_root = settings.sample_codebase_dir.resolve()
    requested_path = Path(file_path)
    candidates = (
        [requested_path.resolve()]
        if requested_path.is_absolute()
        else [
            (sample_root / requested_path).resolve(),
            (settings.base_dir / requested_path).resolve(),
        ]
    )
    source_path = next(
        (
            candidate
            for candidate in candidates
            if candidate.is_relative_to(sample_root)
            and candidate.is_file()
        ),
        None,
    )
    if source_path is None or source_path.suffix.lower() != ".py":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source file not found.")

    source_text = source_path.read_text(encoding="utf-8", errors="replace")
    relative_path = source_path.relative_to(settings.base_dir.resolve()).as_posix()
    security_level = SymbolChunker().determine_security_level(relative_path, source_text)
    if security_level.lower() not in clearance:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")

    numbered_source = "\n".join(
        f'<span id="L{line_number}">{escape(line) or "&nbsp;"}</span>'
        for line_number, line in enumerate(source_text.splitlines(), start=1)
    )
    safe_path = escape(relative_path)
    return HTMLResponse(
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        f"<title>{safe_path}</title></head><body>"
        f"<h1>{safe_path}</h1><pre><code>{numbered_source}</code></pre>"
        "</body></html>"
    )
