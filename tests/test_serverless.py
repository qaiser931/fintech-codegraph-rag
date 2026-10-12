"""Real read-only inference plus API security/contract checks; no live generation."""
import json
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from src.config import settings

TOKENS = {
    "fixture-junior-token-00000": "Junior Dev",
    "fixture-senior-token-00000": "Senior Dev",
    "fixture-security-token-000": "Security Lead",
}

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "api_role_tokens", TOKENS)
    monkeypatch.setattr(settings, "llm_provider", "groq")
    from src.serverless.application import app
    with TestClient(app) as c:
        yield c


def test_real_dense_vectors_are_unit_normalized():
    from src.serverless.application import ASSETS
    vectors = np.load(ASSETS / "vectors.npy", allow_pickle=False)
    assert vectors.shape == (64, 384)
    assert np.allclose(np.linalg.norm(vectors, axis=1), 1, atol=1e-6)


def test_health_supports_original_and_rewritten_path(client):
    for path in ("/api/health", "/api?endpoint=health"):
        data = client.get(path).json()
        assert data["ok"] and data["indexed"]
        assert (data["chunks"], data["graph_nodes"], data["graph_edges"]) == (64, 64, 264)


@pytest.mark.parametrize("role", TOKENS.values())
def test_real_inference_returns_documented_latency_and_only_authorized_sources(client, role):
    from src.security.rbac import rbac_manager
    response = client.post("/api?endpoint=retrieve", json={
        "query": "What is the expected 1LINK latency during peak traffic?", "role": role,
    })
    assert response.status_code == 200, response.text
    data = response.json()
    assert any(c["symbol_name"] == "OneLinkSwitchClient.verify_switch_transaction" for c in data["sources"])
    assert all(c["security_level"] in rbac_manager.get_clearance_for_role(role) for c in data["sources"])
    assert any(i["rerank_score"] is not None for i in data["retrieved_items"])


def test_public_source_response_is_literal_source(client):
    path = "data/sample_codebase/integrations/onelink_client.py"
    response = client.get("/api/source/" + path, params={"role": "Junior Dev"})
    assert response.status_code == 200
    assert response.json()["code"] == Path(path).read_text().rstrip("\n")


def test_junior_cannot_open_confidential_source(client):
    response = client.get("/api/source/data/sample_codebase/auth/webhook_verification.py",
                          params={"role": "Junior Dev"})
    assert response.status_code == 403


@pytest.mark.parametrize("authorization,status", [
    ("Bearer wrong", 401), ("Bearer fixture-senior-token-00000", 403),
])
def test_explicit_invalid_or_mismatched_auth_is_not_overwritten(client, authorization, status):
    response = client.post("/api/retrieve", headers={"Authorization": authorization},
                           json={"query": "1LINK peak latency", "role": "Junior Dev"})
    assert response.status_code == status
    assert "fixture-" not in response.text


@pytest.mark.parametrize("body", [
    {"query": "ab", "role": "Junior Dev"},
    {"query": "latency"},
    {"query": "latency", "role": "invalid"},
    {"query": "latency", "role": "Junior Dev", "stack_trace": 42},
    {"query": "x" * 2001, "role": "Junior Dev"},
])
def test_validation_keeps_ui_error_contract(client, body):
    response = client.post("/api/retrieve", json=body)
    assert response.status_code == 400
    assert isinstance(response.json()["error"], str)


@pytest.mark.parametrize("path", ["../.env", "data/sample_codebase/../secrets.py", "data/sample_codebase/.env"])
def test_source_path_cannot_escape_corpus(client, path):
    response = client.get("/api", params={"endpoint": "source/" + path, "role": "Security Lead"})
    assert response.status_code == 400


def test_facade_never_calls_an_external_backend(client, monkeypatch):
    monkeypatch.setenv("CODEGRAPH_API_URL", "https://attacker.invalid")
    assert client.get("/api/health").json()["ok"]


def test_failure_does_not_expose_configuration(client, monkeypatch):
    import src.serverless.application as module
    def broken():
        raise RuntimeError("secret-provider-key")
    monkeypatch.setattr(module, "initialize", broken)
    response = client.get("/api/health")
    assert response.status_code == 503
    assert "secret-provider-key" not in response.text


def test_dense_tenant_filter_prevents_inference_on_other_tenant(client):
    from src.api.dependencies import app_state
    client.get("/api/health")
    assert app_state.indexer.vector_index.search("latency", tenant_id="other") == []


def test_real_retrieval_query_keeps_grounding_with_one_mocked_groq_completion(client, monkeypatch):
    from src.generation.generator import _PROVIDERS
    from src.telemetry import query_result_cache
    query_result_cache.reset()
    calls = []
    def completion(*args, **kwargs):
        calls.append(1)
        return ("## Direct answer\n1LINK peak latency fluctuates between 2.0s and 6.0s per request [1].\n"
                "Evidence status: Supported", 100, 30)
    monkeypatch.setitem(_PROVIDERS, "groq", completion)
    response = client.post("/api?endpoint=query", json={
        "query": "What is the expected 1LINK latency during peak traffic?", "role": "Junior Dev"})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "SUPPORTED" and data["provider"] == "groq"
    assert "2.0s" in data["answer"] and "6.0s" in data["answer"]
    assert data["citations"] and len(calls) == 1


def test_deployment_rewrites_target_the_index_function_route():
    config = json.loads(Path("vercel.json").read_text())
    routes = {r["source"]: r["destination"] for r in config["rewrites"]}
    assert routes["/api/query"] == "/api?endpoint=query"
    assert routes["/api/source/:file_path*"] == "/api?endpoint=source/:file_path*"


def test_readonly_profile_does_not_create_directories_or_import_torch(tmp_path):
    import os, subprocess, sys
    code = '''
from pathlib import Path
def no_write(*args, **kwargs): raise AssertionError("filesystem write")
Path.mkdir = no_write
import api.index
assert not {"torch", "chromadb", "sentence_transformers"}.intersection(__import__("sys").modules)
'''
    result = subprocess.run([sys.executable, "-c", code], env={**os.environ, "CODEGRAPH_SERVERLESS": "1"},
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
