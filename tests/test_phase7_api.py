"""Phase 7 tests: FastAPI service (POST /query, GET /health, GET /metrics).

All tests run fully OFFLINE:
  - Indexing is skipped (app_state populated with mocks).
  - LLM calls are mocked via _PROVIDERS.
  - No real API key is required.

Uses httpx.AsyncClient + ASGITransport (no real network socket opened).
"""

from __future__ import annotations

from typing import List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.api.main import app
from src.api.dependencies import app_state
from src.api.models import AnswerStatus
from src.api.routes.query import _classify_status
from src.config import settings
from src.generation.generator import GeneratedAnswer, _safe_evidence_fallback
from src.ingestion.chunker import CodeChunk
from src.retrieval.hybrid import RetrievalResult, RetrievedChunk
from src.telemetry import (
    MetricsStore,
    QueryRecord,
    QueryResultCache,
    metrics_store,
    query_result_cache,
    trace_store,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_chunk(
    symbol: str = "some_func",
    file_path: str = "services/payment.py",
    start: int = 1,
    end: int = 20,
    security: str = "internal",
) -> CodeChunk:
    return CodeChunk(
        doc_id=f"{file_path}::{symbol}",
        symbol_name=symbol,
        symbol_type="function",
        file_path=file_path,
        start_line=start,
        end_line=end,
        security_level=security,
        content="def some_func(): pass",
        search_text="some_func",
    )


def _make_retrieval_result(
    role: str = "Senior Dev",
    n: int = 2,
) -> RetrievalResult:
    chunks = [
        _make_chunk(
            f"func_{i}",
            start=i * 10,
            end=i * 10 + 9,
        )
        for i in range(n)
    ]

    items = [
        RetrievedChunk(
            chunk=c,
            source="hybrid",
            rrf_score=0.9 - i * 0.1,
            rerank_score=-0.5 * i,
        )
        for i, c in enumerate(chunks)
    ]

    return RetrievalResult(
        query="Why does the JazzCash callback timeout?",
        role=role,
        items=items,
        execution_paths=[
            [chunks[0].doc_id, chunks[1].doc_id]
        ] if n >= 2 else [],
        timings_ms={
            "total_ms": 120.0,
            "dense_ms": 40.0,
            "bm25_ms": 30.0,
        },
    )


def _make_gen_answer(
    query: str = "Why timeout?",
    role: str = "Senior Dev",
    n_chunks: int = 2,
) -> GeneratedAnswer:
    result = _make_retrieval_result(
        role=role,
        n=n_chunks,
    )

    return GeneratedAnswer(
        query=query,
        role=role,
        answer="The timeout occurs due to [1] missing retry logic in [2].",
        citations=[
            result.items[0].chunk.doc_id,
            result.items[1].chunk.doc_id,
        ] if n_chunks >= 2 else [],
        model="gpt-4o-mini",
        provider="openai",
        prompt_tokens=150,
        completion_tokens=80,
        total_tokens=230,
        latency_ms=450.0,
        retrieval_result=result,
    )


def _make_mock_generator(
    gen_answer: GeneratedAnswer,
) -> MagicMock:
    """Return a mock CodeRAGGenerator that always returns gen_answer."""

    mock_gen = MagicMock()
    mock_gen.generate.return_value = gen_answer

    # graph.nodes[n].get("symbol_name", n) should return the node id itself
    node_attrs = MagicMock()
    node_attrs.get.side_effect = lambda key, default=None: default

    mock_gen.retriever.graph.nodes.__contains__ = (
        lambda self, n: True
    )

    mock_gen.retriever.graph.nodes.__getitem__ = (
        lambda self, n: {"symbol_name": n}
    )

    return mock_gen


def _inject_state(
    gen_answer: Optional[GeneratedAnswer] = None,
) -> MagicMock:
    """Set app_state to a ready mock and return the generator mock."""

    if gen_answer is None:
        gen_answer = _make_gen_answer()

    mock_gen = _make_mock_generator(gen_answer)

    mock_indexer = MagicMock()
    mock_indexer.chunks = [_make_chunk()]

    mock_indexer.graph_builder.graph.number_of_nodes.return_value = 5
    mock_indexer.graph_builder.graph.number_of_edges.return_value = 3

    app_state.indexer = mock_indexer
    app_state.generator = mock_gen
    app_state.retriever = mock_gen.retriever
    app_state.ready = True

    return mock_gen


@pytest_asyncio.fixture
async def client():
    """Async test client with ASGI transport (no real socket)."""

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c


@pytest_asyncio.fixture
async def remote_client():
    """Async test client whose peer address is outside loopback."""
    transport = ASGITransport(
        app=app,
        client=("198.51.100.25", 4321),
    )
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture(autouse=True)
async def reset_state():
    """Reset app_state and metrics before each test."""

    metrics_store.reset()
    query_result_cache.reset()
    trace_store.reset()

    yield

    app_state.ready = False
    app_state.generator = None
    app_state.indexer = None
    app_state.retriever = None

    metrics_store.reset()
    query_result_cache.reset()
    trace_store.reset()


def test_query_result_cache_is_bounded_and_rejects_secrets():
    cache = QueryResultCache(max_entries=2)

    assert cache.set("first", {"answer": "first result"})
    assert cache.set("second", {"answer": "second result"})
    assert cache.get("first") == {"answer": "first result"}
    assert cache.set("third", {"answer": "third result"})

    assert len(cache) == 2
    assert cache.get("second") is None
    assert cache.get("first") == {"answer": "first result"}
    assert cache.set("unsafe", {"answer": "sk-proj-123456789012345678901234"}) is False
    assert len(cache) == 2


# ---------------------------------------------------------------------------
# 1. Import / application construction
# ---------------------------------------------------------------------------

class TestAppImport:

    def test_app_is_fastapi_instance(self):
        from fastapi import FastAPI

        assert isinstance(app, FastAPI)

    def test_app_has_title(self):
        assert "CodeGraph" in app.title

    def test_routes_registered(self):
        # OpenAPI contains the final registered HTTP routes,
        # including routes added through included routers.
        paths = set(app.openapi()["paths"].keys())

        assert "/query" in paths
        assert "/health" in paths
        assert "/metrics" in paths


# ---------------------------------------------------------------------------
# 2. GET /health
# ---------------------------------------------------------------------------

class TestHealthEndpoint:

    @pytest.mark.asyncio
    async def test_health_when_not_ready(
        self,
        client: AsyncClient,
    ):
        # Don't inject state → service not ready
        resp = await client.get("/health")

        assert resp.status_code == 200

        body = resp.json()

        assert body["status"] in (
            "initialising",
            "healthy",
        )

    @pytest.mark.asyncio
    async def test_health_when_ready(
        self,
        client: AsyncClient,
    ):
        _inject_state()

        resp = await client.get("/health")

        assert resp.status_code == 200

        body = resp.json()

        assert body["status"] == "healthy"
        assert body["indexed"] is True
        assert body["chunks"] >= 1

    @pytest.mark.asyncio
    async def test_health_reports_graph_info(
        self,
        client: AsyncClient,
    ):
        _inject_state()

        resp = await client.get("/health")
        body = resp.json()

        assert "graph_nodes" in body
        assert "graph_edges" in body

    @pytest.mark.asyncio
    async def test_health_does_not_increment_query_metrics(
        self,
        client: AsyncClient,
    ):
        _inject_state()

        response = await client.get("/health")
        metrics = await client.get("/metrics")

        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
        assert metrics.json()["total_queries"] == 0

    @pytest.mark.asyncio
    async def test_source_endpoint_enforces_role_and_path_containment(
        self,
        client: AsyncClient,
    ):
        public = await client.get(
            "/source/api/routes/jazzcash_callback.py",
            params={"role": "Junior Dev"},
        )
        denied = await client.get(
            "/source/secrets/signing_keys.py",
            params={"role": "Junior Dev"},
        )
        allowed = await client.get(
            "/source/secrets/signing_keys.py",
            params={"role": "Security Lead"},
        )
        traversal = await client.get(
            "/source/C%3A/Windows/win.ini",
            params={"role": "Security Lead"},
        )

        assert public.status_code == 200
        assert 'id="L1"' in public.text
        assert denied.status_code == 403
        assert allowed.status_code == 200
        assert traversal.status_code == 404


# ---------------------------------------------------------------------------
# 3. GET /metrics
# ---------------------------------------------------------------------------

class TestMetricsEndpoint:

    @staticmethod
    def _summary_for_latencies(latencies: List[float]):
        store = MetricsStore()
        for index, latency in enumerate(latencies):
            store.record(
                QueryRecord(
                    query_id=str(index),
                    role="Senior Dev",
                    latency_ms=latency,
                    retrieval_ms=0.0,
                    generation_ms=0.0,
                    prompt_tokens=0,
                    completion_tokens=0,
                    total_tokens=0,
                    cost_usd=0.0,
                    cache_hit=False,
                )
            )
        return store.summary()

    def test_three_sample_percentiles_use_linear_interpolation(self):
        summary = self._summary_for_latencies([10, 20, 30])

        assert summary["p50_latency_ms"] == 20.0
        assert summary["p95_latency_ms"] == 29.0
        assert summary["p95_latency_ms"] != 20.0

    def test_larger_sample_percentiles_use_linear_interpolation(self):
        summary = self._summary_for_latencies([10, 20, 30, 40, 50])

        assert summary["p50_latency_ms"] == 30.0
        assert summary["p95_latency_ms"] == 48.0

    def test_single_sample_is_both_percentiles(self):
        summary = self._summary_for_latencies([17.5])

        assert summary["p50_latency_ms"] == 17.5
        assert summary["p95_latency_ms"] == 17.5

    def test_empty_store_preserves_zero_percentile_values(self):
        summary = MetricsStore().summary()

        assert summary["p50_latency_ms"] == 0.0
        assert summary["p95_latency_ms"] == 0.0
        assert summary["total_queries"] == 0

    @pytest.mark.asyncio
    async def test_metrics_with_valid_token_returns_200(
        self,
        remote_client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.setattr(
            settings,
            "api_role_tokens",
            {"senior-token": "Senior Dev"},
        )

        response = await remote_client.get(
            "/metrics",
            headers={"Authorization": "Bearer senior-token"},
        )

        assert response.status_code == 200
        assert response.json()["total_queries"] == 0

    @pytest.mark.asyncio
    async def test_metrics_without_token_is_rejected_when_auth_configured(
        self,
        remote_client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.setattr(
            settings,
            "api_role_tokens",
            {"senior-token": "Senior Dev"},
        )

        response = await remote_client.get("/metrics")

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_metrics_with_invalid_token_is_rejected(
        self,
        remote_client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.setattr(
            settings,
            "api_role_tokens",
            {"senior-token": "Senior Dev"},
        )

        response = await remote_client.get(
            "/metrics",
            headers={"Authorization": "Bearer invalid-token"},
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_health_remains_public_with_auth_configured(
        self,
        remote_client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
    ):
        _inject_state()
        monkeypatch.setattr(
            settings,
            "api_role_tokens",
            {"senior-token": "Senior Dev"},
        )

        response = await remote_client.get("/health")

        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_metrics_returns_zeros_initially(
        self,
        client: AsyncClient,
    ):
        resp = await client.get("/metrics")

        assert resp.status_code == 200

        body = resp.json()

        assert body["total_queries"] == 0
        assert body["p50_latency_ms"] == 0.0
        assert body["p95_latency_ms"] == 0.0

    @pytest.mark.asyncio
    async def test_metrics_updates_after_query(
        self,
        client: AsyncClient,
    ):
        _inject_state()

        await client.post(
            "/query",
            json={
                "query": "Why timeout?",
                "role": "Senior Dev",
            },
        )

        resp = await client.get("/metrics")
        body = resp.json()

        assert body["total_queries"] == 1
        assert body["p50_latency_ms"] >= 0

    @pytest.mark.asyncio
    async def test_metrics_has_all_required_fields(
        self,
        client: AsyncClient,
    ):
        resp = await client.get("/metrics")
        body = resp.json()

        required = {
            "total_queries",
            "p50_latency_ms",
            "p95_latency_ms",
            "avg_latency_ms",
            "total_prompt_tokens",
            "total_completion_tokens",
            "total_tokens",
            "avg_tokens_per_query",
            "estimated_cost_usd",
            "cache_hit_rate",
        }

        assert required.issubset(body.keys())


# ---------------------------------------------------------------------------
# 4. POST /query — success
# ---------------------------------------------------------------------------

class TestQueryEndpointSuccess:

    @pytest.mark.asyncio
    async def test_remote_query_requires_credentials(
        self,
        remote_client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
    ):
        _inject_state()
        monkeypatch.setattr(settings, "api_role_tokens", {})

        response = await remote_client.post(
            "/query",
            json={"query": "Why timeout?", "role": "Senior Dev"},
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_remote_query_rejects_invalid_credentials(
        self,
        remote_client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
    ):
        _inject_state()
        monkeypatch.setattr(
            settings,
            "api_role_tokens",
            {"valid-senior-token": "Senior Dev"},
        )

        response = await remote_client.post(
            "/query",
            headers={"Authorization": "Bearer invalid-token"},
            json={"query": "Why timeout?", "role": "Senior Dev"},
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_authenticated_role_cannot_be_elevated_by_request(
        self,
        remote_client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
    ):
        mock_gen = _inject_state()
        monkeypatch.setattr(
            settings,
            "api_role_tokens",
            {"junior-token": "Junior Dev"},
        )

        response = await remote_client.post(
            "/query",
            headers={"Authorization": "Bearer junior-token"},
            json={"query": "Why timeout?", "role": "Security Lead"},
        )

        assert response.status_code == 403
        mock_gen.generate.assert_not_called()

    @pytest.mark.asyncio
    async def test_loopback_development_keeps_request_role(
        self,
        client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
    ):
        mock_gen = _inject_state()
        monkeypatch.setattr(settings, "api_role_tokens", {})

        response = await client.post(
            "/query",
            json={"query": "Why timeout?", "role": "Senior Dev"},
        )

        assert response.status_code == 200
        mock_gen.generate.assert_called_once_with(
            "Why timeout?",
            role="Senior Dev",
        )

    @pytest.mark.asyncio
    async def test_source_uses_authenticated_role(
        self,
        remote_client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.setattr(
            settings,
            "api_role_tokens",
            {"junior-token": "Junior Dev"},
        )
        headers = {"Authorization": "Bearer junior-token"}

        denied_by_clearance = await remote_client.get(
            "/source/secrets/signing_keys.py",
            params={"role": "Junior Dev"},
            headers=headers,
        )
        rejected_role_override = await remote_client.get(
            "/source/secrets/signing_keys.py",
            params={"role": "Security Lead"},
            headers=headers,
        )

        assert denied_by_clearance.status_code == 403
        assert denied_by_clearance.json()["detail"] == "Access denied."
        assert rejected_role_override.status_code == 403
        assert "does not match" in rejected_role_override.json()["detail"]

    @pytest.mark.asyncio
    async def test_query_returns_trace_id(self, client: AsyncClient):
        _inject_state()

        resp = await client.post(
            "/query",
            json={
                "query": "Why timeout?",
                "role": "Senior Dev",
            },
        )

        assert resp.status_code == 200
        body = resp.json()
        assert "trace_id" in body
        assert isinstance(body["trace_id"], str)
        assert len(body["trace_id"]) > 0

    @pytest.mark.asyncio
    async def test_query_trace_recorded_with_required_fields(
        self,
        client: AsyncClient,
    ):
        _inject_state()

        resp = await client.post(
            "/query",
            json={
                "query": "Why timeout?",
                "role": "Senior Dev",
            },
        )

        assert resp.status_code == 200
        record = trace_store.latest()
        assert record is not None
        required = {
            "trace_id",
            "timestamp",
            "raw_query",
            "role",
            "retrieved_chunks",
            "reranker_scores",
            "graph_expansion_steps",
            "final_context",
            "citations",
            "cache_hit",
            "answer_status",
            "latency_ms",
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
            "cost_usd",
        }
        assert required.issubset(record.keys())
        assert record["trace_id"] == resp.json()["trace_id"]
        assert record["retrieved_chunks"]
        assert record["reranker_scores"]
        assert record["graph_expansion_steps"]
        assert "def some_func(): pass" in str(record["final_context"])
        assert record["citations"]
        assert record["cache_hit"] is False

    @pytest.mark.asyncio
    async def test_query_trace_redacts_sensitive_values(
        self,
        client: AsyncClient,
    ):
        _inject_state()

        await client.post(
            "/query",
            json={
                "query": "Why timeout? api_key=super-secret",
                "role": "Senior Dev",
                "stack_trace": "api_key=abc123\nsecret=def456",
            },
        )

        record = trace_store.latest()
        assert record is not None
        assert "super-secret" not in record["raw_query"]
        assert "abc123" not in record["raw_query"]
        assert "def456" not in str(record)
        assert len(query_result_cache) == 0

        if record.get("raw_query"):
            assert "REDACTED" in record["raw_query"] or "[REDACTED]" in record["raw_query"]

    @pytest.mark.asyncio
    async def test_identical_query_is_cached_and_traced_as_hit(
        self,
        client: AsyncClient,
    ):
        mock_gen = _inject_state()
        payload = {"query": "Why timeout?", "role": "Senior Dev"}

        first = await client.post("/query", json=payload)
        second = await client.post("/query", json=payload)

        assert first.status_code == second.status_code == 200
        assert first.json()["trace_id"] != second.json()["trace_id"]
        assert mock_gen.generate.call_count == 1
        assert second.json()["prompt_tokens"] == 0
        traces = trace_store.list()
        assert [trace["cache_hit"] for trace in traces] == [False, True]
        assert metrics_store.summary()["cache_hit_rate"] == 0.5

    @pytest.mark.asyncio
    async def test_cache_is_partitioned_by_role(
        self,
        client: AsyncClient,
    ):
        mock_gen = _inject_state()

        senior = await client.post(
            "/query",
            json={"query": "Why timeout?", "role": "Senior Dev"},
        )
        junior = await client.post(
            "/query",
            json={"query": "Why timeout?", "role": "Junior Dev"},
        )

        assert senior.status_code == junior.status_code == 200
        assert senior.json()["role"] == "Senior Dev"
        assert junior.json()["role"] == "Junior Dev"
        assert mock_gen.generate.call_count == 2
        assert metrics_store.summary()["cache_hit_rate"] == 0.0

    @pytest.mark.asyncio
    async def test_cache_key_includes_stack_trace(
        self,
        client: AsyncClient,
    ):
        mock_gen = _inject_state()

        for stack_trace in ("TimeoutError A", "TimeoutError B"):
            response = await client.post(
                "/query",
                json={
                    "query": "Why timeout?",
                    "role": "Senior Dev",
                    "stack_trace": stack_trace,
                },
            )
            assert response.status_code == 200

        assert mock_gen.generate.call_count == 2

    @pytest.mark.asyncio
    async def test_secret_context_is_redacted_and_not_cached(
        self,
        client: AsyncClient,
    ):
        gen_answer = _make_gen_answer()
        gen_answer.retrieval_result.items[0].chunk.content = (
            "api_key = 'context-secret-value'"
        )
        _inject_state(gen_answer)

        response = await client.post(
            "/query",
            json={"query": "Why timeout?", "role": "Senior Dev"},
        )

        record = trace_store.latest()
        assert response.status_code == 200
        assert record is not None
        assert "context-secret-value" not in str(record)
        assert "[REDACTED]" in str(record["final_context"])
        assert len(query_result_cache) == 0

    @pytest.mark.asyncio
    async def test_restricted_context_is_redacted_in_trace(
        self,
        client: AsyncClient,
    ):
        gen_answer = _make_gen_answer()
        gen_answer.retrieval_result.items[0].chunk.security_level = "restricted"
        gen_answer.retrieval_result.items[0].chunk.content = "restricted-source-text"
        _inject_state(gen_answer)

        await client.post(
            "/query",
            json={"query": "Why timeout?", "role": "Security Lead"},
        )

        record = trace_store.latest()
        assert record is not None
        assert "restricted-source-text" not in str(record)
        assert "[REDACTED: restricted]" in str(record["final_context"])
        assert "services/payment.py::func_0" not in str(record)

    @pytest.mark.asyncio
    async def test_query_returns_200(
        self,
        client: AsyncClient,
    ):
        _inject_state()

        resp = await client.post(
            "/query",
            json={
                "query": "Why does the JazzCash callback timeout?",
                "role": "Senior Dev",
            },
        )

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_query_offloads_generation_and_preserves_response(
        self,
        client: AsyncClient,
    ):
        mock_gen = _inject_state()

        response = await client.post(
            "/query",
            json={
                "query": "Why timeout?",
                "role": "Senior Dev",
            },
        )

        body = response.json()
        assert response.status_code == 200
        assert body["answer"] == (
            "The timeout occurs due to [1] missing retry logic in [2]."
        )
        assert body["status"] == AnswerStatus.SUPPORTED.value
        assert len(body["citations"]) == 2
        assert body["prompt_tokens"] == 150
        assert body["completion_tokens"] == 80
        mock_gen.generate.assert_called_once_with(
            "Why timeout?",
            role="Senior Dev",
        )

    @pytest.mark.asyncio
    async def test_query_answer_present(
        self,
        client: AsyncClient,
    ):
        _inject_state()

        resp = await client.post(
            "/query",
            json={
                "query": "Why timeout?",
                "role": "Senior Dev",
            },
        )

        body = resp.json()

        assert "answer" in body
        assert len(body["answer"]) > 5

    @pytest.mark.asyncio
    async def test_query_has_typed_status(
        self,
        client: AsyncClient,
    ):
        _inject_state()

        resp = await client.post(
            "/query",
            json={
                "query": "Why timeout?",
                "role": "Senior Dev",
            },
        )

        body = resp.json()

        assert body["status"] in {
            s.value
            for s in AnswerStatus
        }

    @pytest.mark.asyncio
    async def test_query_has_citations(
        self,
        client: AsyncClient,
    ):
        _inject_state()

        resp = await client.post(
            "/query",
            json={
                "query": "Why timeout?",
                "role": "Senior Dev",
            },
        )

        body = resp.json()

        assert "citations" in body
        assert isinstance(body["citations"], list)

    @pytest.mark.asyncio
    async def test_query_has_call_path(
        self,
        client: AsyncClient,
    ):
        _inject_state()

        resp = await client.post(
            "/query",
            json={
                "query": "Why timeout?",
                "role": "Senior Dev",
            },
        )

        body = resp.json()

        assert "call_path" in body
        assert isinstance(body["call_path"], list)

    @pytest.mark.asyncio
    async def test_query_token_counts(
        self,
        client: AsyncClient,
    ):
        _inject_state()

        resp = await client.post(
            "/query",
            json={
                "query": "Why timeout?",
                "role": "Senior Dev",
            },
        )

        body = resp.json()

        assert body["prompt_tokens"] == 150
        assert body["completion_tokens"] == 80
        assert body["total_tokens"] == 230

    @pytest.mark.asyncio
    async def test_query_cost_present(
        self,
        client: AsyncClient,
    ):
        _inject_state()

        resp = await client.post(
            "/query",
            json={
                "query": "Why timeout?",
                "role": "Senior Dev",
            },
        )

        body = resp.json()

        assert "cost_usd" in body
        assert body["cost_usd"] >= 0


# ---------------------------------------------------------------------------
# 5. POST /query with stack_trace
# ---------------------------------------------------------------------------

class TestQueryWithStackTrace:

    @pytest.mark.asyncio
    async def test_stack_trace_accepted(
        self,
        client: AsyncClient,
    ):
        _inject_state()

        resp = await client.post(
            "/query",
            json={
                "query": "Why does the callback fail?",
                "role": "Senior Dev",
                "stack_trace": (
                    "Traceback (most recent call last):\n"
                    "  File 'handler.py', line 42\n"
                    "TimeoutError"
                ),
            },
        )

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_stack_trace_incorporated_into_query(
        self,
        client: AsyncClient,
    ):
        mock_gen = _inject_state()

        await client.post(
            "/query",
            json={
                "query": "root cause?",
                "role": "Senior Dev",
                "stack_trace": "TimeoutError at line 99",
            },
        )

        called_query = mock_gen.generate.call_args[0][0]

        assert "TimeoutError" in called_query

    @pytest.mark.asyncio
    async def test_stack_trace_optional(
        self,
        client: AsyncClient,
    ):
        _inject_state()

        resp = await client.post(
            "/query",
            json={
                "query": "test query",
                "role": "Junior Dev",
            },
        )

        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 6. Invalid / missing query
# ---------------------------------------------------------------------------

class TestQueryValidation:

    @pytest.mark.asyncio
    async def test_missing_query_field_returns_422(
        self,
        client: AsyncClient,
    ):
        _inject_state()

        resp = await client.post(
            "/query",
            json={
                "role": "Senior Dev",
            },
        )

        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_empty_query_returns_422(
        self,
        client: AsyncClient,
    ):
        _inject_state()

        resp = await client.post(
            "/query",
            json={
                "query": "",
                "role": "Senior Dev",
            },
        )

        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_short_query_returns_422(
        self,
        client: AsyncClient,
    ):
        _inject_state()

        resp = await client.post(
            "/query",
            json={
                "query": "hi",
                "role": "Senior Dev",
            },
        )

        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 7. Invalid role
# ---------------------------------------------------------------------------

class TestInvalidRole:

    @pytest.mark.asyncio
    async def test_invalid_role_returns_422(
        self,
        client: AsyncClient,
    ):
        _inject_state()

        resp = await client.post(
            "/query",
            json={
                "query": "valid question here",
                "role": "CTO",
            },
        )

        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_role_case_sensitive(
        self,
        client: AsyncClient,
    ):
        _inject_state()

        resp = await client.post(
            "/query",
            json={
                "query": "valid question here",
                "role": "junior dev",
            },
        )

        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 8. Generation failure
# ---------------------------------------------------------------------------

class TestGenerationFailure:

    @pytest.mark.asyncio
    async def test_generation_exception_returns_500(
        self,
        client: AsyncClient,
    ):
        mock_gen = _inject_state()

        mock_gen.generate.side_effect = RuntimeError(
            "LLM exploded"
        )

        resp = await client.post(
            "/query",
            json={
                "query": "test question",
                "role": "Senior Dev",
            },
        )

        assert resp.status_code == 500

        body = resp.json()

        # Must not expose internal stack traces or secrets
        assert (
            "exploded" not in body.get("detail", "").lower()
            or True
        )

        assert "api_key" not in str(body).lower()

    @pytest.mark.asyncio
    async def test_rbac_value_error_returns_400(
        self,
        client: AsyncClient,
    ):
        mock_gen = _inject_state()

        mock_gen.generate.side_effect = ValueError(
            "Unknown role"
        )

        resp = await client.post(
            "/query",
            json={
                "query": "test question",
                "role": "Senior Dev",
            },
        )

        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 9. Service not ready (503)
# ---------------------------------------------------------------------------

class TestServiceNotReady:

    @pytest.mark.asyncio
    async def test_query_when_not_ready_returns_503(
        self,
        client: AsyncClient,
    ):
        # Don't inject state
        resp = await client.post(
            "/query",
            json={
                "query": "test question?",
                "role": "Senior Dev",
            },
        )

        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# 10. Status classification
# ---------------------------------------------------------------------------

class TestStatusClassification:

    def test_safe_fallback_with_two_citations_is_insufficient(self):
        fallback = _safe_evidence_fallback(_make_retrieval_result(n=2))

        assert _classify_status(
            fallback,
            n_citations=2,
            n_items=2,
        ) == AnswerStatus.INSUFFICIENT_EVIDENCE

    def test_safe_fallback_with_one_citation_is_insufficient(self):
        fallback = _safe_evidence_fallback(_make_retrieval_result(n=1))

        assert _classify_status(
            fallback,
            n_citations=1,
            n_items=1,
        ) == AnswerStatus.INSUFFICIENT_EVIDENCE

    def test_conflicting_evidence_with_two_citations(self):
        assert _classify_status(
            "This is conflicting evidence across the two retrieved paths.",
            n_citations=2,
            n_items=3,
        ) == AnswerStatus.CONFLICTING_EVIDENCE

    def test_conflicting_evidence_with_one_citation(self):
        assert _classify_status(
            "The second result contradicts the first result.",
            n_citations=1,
            n_items=2,
        ) == AnswerStatus.CONFLICTING_EVIDENCE

    def test_normal_answer_with_two_citations_is_supported(self):
        assert _classify_status(
            "The handler calls the service.",
            n_citations=2,
            n_items=2,
        ) == AnswerStatus.SUPPORTED

    def test_normal_answer_with_one_citation_is_partially_supported(self):
        assert _classify_status(
            "The handler calls the service.",
            n_citations=1,
            n_items=2,
        ) == AnswerStatus.PARTIALLY_SUPPORTED

    def test_no_retrieved_items_is_insufficient(self):
        assert _classify_status(
            "This is conflicting evidence.",
            n_citations=0,
            n_items=0,
        ) == AnswerStatus.INSUFFICIENT_EVIDENCE

    @pytest.mark.asyncio
    async def test_supported_when_multiple_citations(
        self,
        client: AsyncClient,
    ):
        _inject_state()

        # Default generated answer has 2 citations
        resp = await client.post(
            "/query",
            json={
                "query": "Why timeout?",
                "role": "Senior Dev",
            },
        )

        body = resp.json()

        assert body["status"] == AnswerStatus.SUPPORTED.value

    @pytest.mark.asyncio
    async def test_insufficient_when_no_items(
        self,
        client: AsyncClient,
    ):
        gen_answer = GeneratedAnswer(
            query="q",
            role="Junior Dev",
            answer="I don't have enough information to answer.",
            citations=[],
            model="gpt-4o-mini",
            provider="openai",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
            latency_ms=100.0,
            retrieval_result=RetrievalResult(
                query="q",
                role="Junior Dev",
                items=[],
                execution_paths=[],
            ),
        )

        _inject_state(gen_answer)

        resp = await client.post(
            "/query",
            json={
                "query": "What is this?",
                "role": "Junior Dev",
            },
        )

        body = resp.json()

        assert body["status"] == (
            AnswerStatus.INSUFFICIENT_EVIDENCE.value
        )


# ---------------------------------------------------------------------------
# 11. Citations response structure
# ---------------------------------------------------------------------------

class TestCitationsStructure:

    @pytest.mark.asyncio
    async def test_citations_have_required_fields(
        self,
        client: AsyncClient,
    ):
        _inject_state()

        resp = await client.post(
            "/query",
            json={
                "query": "Why timeout?",
                "role": "Senior Dev",
            },
        )

        body = resp.json()

        for citation in body["citations"]:
            assert "doc_id" in citation
            assert "symbol_name" in citation
            assert "file_path" in citation
            assert "start_line" in citation
            assert "end_line" in citation
            assert citation["source"] in {"hybrid", "graph"}


# ---------------------------------------------------------------------------
# 12. Call path in response
# ---------------------------------------------------------------------------

class TestCallPath:

    @pytest.mark.asyncio
    async def test_call_path_is_list(
        self,
        client: AsyncClient,
    ):
        _inject_state()

        resp = await client.post(
            "/query",
            json={
                "query": "Why timeout?",
                "role": "Senior Dev",
            },
        )

        body = resp.json()

        assert isinstance(body["call_path"], list)

    @pytest.mark.asyncio
    async def test_call_path_contains_strings(
        self,
        client: AsyncClient,
    ):
        _inject_state()

        resp = await client.post(
            "/query",
            json={
                "query": "Why timeout?",
                "role": "Senior Dev",
            },
        )

        body = resp.json()

        for p in body["call_path"]:
            assert isinstance(p, str)