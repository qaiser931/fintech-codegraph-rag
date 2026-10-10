"""Retrieval endpoint tests with no model loading, sockets or generation."""
import asyncio
import threading
from unittest.mock import MagicMock

import networkx as nx
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.api.dependencies import app_state
from src.api.main import app
from src.config import settings
from src.ingestion.chunker import CodeChunk
from src.retrieval.hybrid import RetrievalResult, RetrievedChunk
from src.telemetry import metrics_store


@pytest.fixture
def pipeline(monkeypatch):
    graph = nx.DiGraph()
    chunks = []
    for name in ("callback", "payment"):
        chunk = CodeChunk(doc_id=name, symbol_name=name, symbol_type="function",
                          file_path="services/payment.py", start_line=1, end_line=3,
                          security_level="internal", content="PRIVATE SOURCE", search_text=name)
        chunks.append(RetrievedChunk(chunk=chunk, source="hybrid", rrf_score=0.5))
        graph.add_node(name, symbol_name=name, security_level="internal")
    result = RetrievalResult(query="Why timeout?", role="Senior Dev", items=chunks,
                             execution_paths=[["callback", "payment"]], timings_ms={"total_ms": 5})
    retriever = MagicMock(graph=graph)
    retriever.retrieve.return_value = result
    indexer = MagicMock(chunks=[i.chunk for i in chunks])
    indexer.graph_builder.graph = graph
    monkeypatch.setattr(app_state, "ready", True)
    monkeypatch.setattr(app_state, "retriever", retriever)
    monkeypatch.setattr(app_state, "generator", MagicMock())
    monkeypatch.setattr(app_state, "indexer", indexer)
    metrics_store.reset()
    yield retriever
    metrics_store.reset()


@pytest_asyncio.fixture
async def client(pipeline):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_evidence_only_no_generation_or_query_metrics(client, pipeline):
    response = await client.post("/retrieve", json={"query": "Why timeout?", "role": "Senior Dev"})
    assert response.status_code == 200
    data = response.json()
    assert data["role"] == "Senior Dev"
    assert len(data["sources"]) == len(data["retrieved_items"]) == 2
    assert data["call_path"] == ["callback → payment"]
    assert data["latency_ms"] >= 0
    assert not {"answer", "status", "provider", "model", "total_tokens", "cost_usd"} & data.keys()
    assert "PRIVATE SOURCE" not in response.text
    pipeline.retrieve.assert_called_once_with("Why timeout?", role="Senior Dev")
    app_state.generator.generate.assert_not_called()
    assert (await client.get("/metrics")).json()["total_queries"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("headers,body_role,expected", [
    ({}, "Senior Dev", 401),
    ({"Authorization": "Bearer invalid"}, "Senior Dev", 401),
    ({"Authorization": "Bearer test-senior"}, "Junior Dev", 403),
    ({"Authorization": "Bearer test-senior"}, "Senior Dev", 200),
    ({"Authorization": "Bearer test-senior"}, None, 200),
])
async def test_token_role_binding(client, pipeline, monkeypatch, headers, body_role, expected):
    monkeypatch.setattr(settings, "api_role_tokens", {"test-senior": "Senior Dev"})
    body = {"query": "Why timeout?"}
    if body_role is not None:
        body["role"] = body_role
    response = await client.post("/retrieve", json=body, headers=headers)
    assert response.status_code == expected
    if expected == 200:
        assert response.json()["role"] == "Senior Dev"
        assert pipeline.retrieve.call_args.kwargs["role"] == "Senior Dev"
    else:
        pipeline.retrieve.assert_not_called()


@pytest.mark.asyncio
async def test_remote_development_request_rejected(pipeline):
    async with AsyncClient(transport=ASGITransport(app=app, client=("198.51.100.8", 123)), base_url="http://test") as c:
        assert (await c.post("/retrieve", json={"query": "Why timeout?"})).status_code == 401
    pipeline.retrieve.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [{}, {"query": "ab"}, {"query": "q" * 2001}, {"query": "Why?", "role": "admin"}])
async def test_request_validation(client, pipeline, body):
    assert (await client.post("/retrieve", json=body)).status_code == 422
    pipeline.retrieve.assert_not_called()


@pytest.mark.asyncio
async def test_optional_stack_trace_and_empty_result(client, pipeline):
    pipeline.retrieve.return_value.items = []
    pipeline.retrieve.return_value.execution_paths = []
    response = await client.post("/retrieve", json={"query": "Why?", "stack_trace": "TimeoutError"})
    assert response.status_code == 200
    assert response.json()["sources"] == response.json()["call_path"] == []
    assert "TimeoutError" in pipeline.retrieve.call_args.args[0]
    assert pipeline.retrieve.call_args.kwargs["role"] == "Junior Dev"


@pytest.mark.asyncio
async def test_unavailable_retriever_without_generator_dependency(client, pipeline, monkeypatch):
    monkeypatch.setattr(app_state, "generator", None)
    assert (await client.post("/retrieve", json={"query": "Why?"})).status_code == 200
    monkeypatch.setattr(app_state, "retriever", None)
    assert (await client.post("/retrieve", json={"query": "Why?"})).status_code == 503


@pytest.mark.asyncio
@pytest.mark.parametrize("target", ["chunk", "path", "unknown-node"])
async def test_unauthorized_evidence_fails_closed(client, pipeline, target):
    if target == "chunk":
        pipeline.retrieve.return_value.items[0].chunk.security_level = "restricted"
    elif target == "path":
        pipeline.graph.nodes["payment"]["security_level"] = "restricted"
    else:
        pipeline.retrieve.return_value.execution_paths = [["callback", "SECRET NODE"]]
    response = await client.post("/retrieve", json={"query": "Why?", "role": "Junior Dev"})
    assert response.status_code == 500
    assert response.json() == {"detail": "Code retrieval failed."}
    assert "SECRET" not in response.text


@pytest.mark.asyncio
async def test_exception_details_are_not_exposed(client, pipeline):
    pipeline.retrieve.side_effect = RuntimeError("token=secret; private source")
    response = await client.post("/retrieve", json={"query": "Why?"})
    assert response.status_code == 500
    assert response.json()["detail"] == "Code retrieval failed."


@pytest.mark.asyncio
async def test_health_responds_while_retrieval_worker_waits(client, pipeline):
    entered, release = threading.Event(), threading.Event()
    result = pipeline.retrieve.return_value
    def blocking(*args, **kwargs):
        entered.set()
        if not release.wait(3):
            raise RuntimeError("Test worker was not released")
        return result
    pipeline.retrieve.side_effect = blocking
    request = asyncio.create_task(client.post("/retrieve", json={"query": "Why?"}))
    try:
        for _ in range(100):
            if entered.is_set():
                break
            await asyncio.sleep(0.01)
        assert entered.is_set()
        health = await asyncio.wait_for(client.get("/health"), timeout=0.5)
        assert health.status_code == 200
        assert health.json()["status"] == "healthy"
        assert not request.done()
    finally:
        release.set()
        response = await request
    assert response.status_code == 200
