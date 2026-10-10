"""Unit tests for Phase 4: Dense Vector Index, BM25 Index, RBAC Filtering, and Metadata Tagging."""

from pathlib import Path

import pytest

from src.config import settings
from src.ingestion.indexer import CodebaseIndexer
from src.retrieval.bm25 import tokenize_code

ALLOWED = {
    "Junior Dev": {"public", "internal"},
    "Senior Dev": {"public", "internal", "confidential"},
    "Security Lead": {"public", "internal", "confidential", "restricted"},
}


@pytest.fixture(scope="module")
def indexed_system() -> CodebaseIndexer:
    indexer = CodebaseIndexer()
    indexer.index_codebase(settings.sample_codebase_dir, base_dir=settings.base_dir)
    return indexer


def test_code_tokenizer_handles_camel_case_and_symbols() -> None:
    """Verify code tokenizer splits identifiers correctly."""
    tokens = tokenize_code("PaymentService.process_jazzcash_callback() -> 'SELECT FOR UPDATE'")
    assert "paymentservice" in tokens or "payment" in tokens
    assert "process" in tokens
    assert "jazzcash" in tokens
    assert "callback" in tokens
    assert "select" in tokens
    assert "update" in tokens


def test_bm25_exact_symbol_search(indexed_system: CodebaseIndexer) -> None:
    """Test BM25 precision on exact symbol names."""
    bm25 = indexed_system.bm25_index
    results = bm25.search("acquire_account_lock", role="Senior Dev", top_k=5)

    assert len(results) > 0
    top_chunk, score = results[0]
    assert "acquire_account_lock" in top_chunk.symbol_name
    assert score > 0.0


def test_bm25_rbac_pre_retrieval_filtering(indexed_system: CodebaseIndexer) -> None:
    """Unauthorized roles NEVER see restricted or confidential symbols in BM25."""
    bm25 = indexed_system.bm25_index

    junior_results = bm25.search("SigningKeyStore JAZZCASH_HMAC_SECRET", role="Junior Dev", top_k=5)
    for chunk, _ in junior_results:
        assert chunk.security_level != "restricted"
        assert chunk.security_level != "confidential"
        assert "secrets/signing_keys.py" not in chunk.file_path

    lead_results = bm25.search("SigningKeyStore JAZZCASH_HMAC_SECRET", role="Security Lead", top_k=5)
    assert any(c.security_level == "restricted" for c, _ in lead_results)


def test_dense_vector_search_and_rbac_filtering(indexed_system: CodebaseIndexer) -> None:
    """Dense retrieval works and respects clearance."""
    vec_index = indexed_system.vector_index

    results = vec_index.search(
        "why does jazzcash callback throw timeout error during peak traffic",
        role="Senior Dev",
        top_k=5,
    )
    assert len(results) > 0

    _, score = results[0]
    assert score > 0.0
    for chunk, _ in results:
        assert chunk.security_level != "restricted"


def test_dense_vector_strict_isolation_for_junior_dev(indexed_system: CodebaseIndexer) -> None:
    """Junior Dev only ever receives public and internal chunks."""
    vec_index = indexed_system.vector_index
    results = vec_index.search(
        "signing keys and webhook verification HMAC secret", role="Junior Dev", top_k=10
    )

    for chunk, _ in results:
        assert chunk.security_level in ["public", "internal"]
        assert "secrets/" not in chunk.file_path
        assert "auth/" not in chunk.file_path


def test_indexer_disk_persistence_roundtrip(tmp_path: Path) -> None:
    """Verify saving and reloading indices from disk (ChromaDB persistent store)."""
    indexer = CodebaseIndexer()
    indexer.index_codebase(settings.sample_codebase_dir, base_dir=settings.base_dir)

    g_file = tmp_path / "graph.json"
    b_file = tmp_path / "bm25.pkl"
    v_dir = tmp_path / "vectors"

    indexer.graph_builder.save_graph(g_file)
    indexer.bm25_index.save_index(b_file)
    indexer.vector_index.save_index(v_dir)

    assert g_file.exists()
    assert b_file.exists()
    assert (v_dir / "chroma.sqlite3").exists()

    reloaded = CodebaseIndexer()
    reloaded.graph_builder.load_graph(g_file)
    reloaded.bm25_index.load_index(b_file)
    reloaded.vector_index.load_index(v_dir)

    assert len(reloaded.bm25_index.chunks) == len(indexer.chunks)
    assert len(reloaded.vector_index.chunks) == len(indexer.chunks)


# ---------------------------------------------------------------------------
# Phase 4b: real embeddings + ChromaDB + in-query RBAC
# ---------------------------------------------------------------------------


def test_uses_real_neural_model(indexed_system: CodebaseIndexer) -> None:
    """The dense index must use the real BGE model, not the hash-based fallback."""
    engine = indexed_system.vector_index.engine
    assert engine.__class__.__name__ == "SentenceTransformerEmbeddingEngine"
    assert engine.dimension == 384


def test_semantic_query_finds_lock_symbol(indexed_system: CodebaseIndexer) -> None:
    """Dense search should surface the lock-related symbol from a natural-language query."""
    hits = indexed_system.vector_index.search(
        "code that holds a database lock while making a network call",
        role="Senior Dev",
        top_k=8,
    )
    doc_ids = [c.doc_id for c, _ in hits]
    assert any("acquire_account_lock" in d for d in doc_ids), doc_ids


@pytest.mark.xfail(
    reason="Single-vector search ranks lock-related symbols; the buggy caller "
    "process_jazzcash_callback is reached via graph expansion (Phase 5).",
    strict=False,
)
def test_dense_only_finds_buggy_caller(indexed_system: CodebaseIndexer) -> None:
    """Known limitation of vector-only retrieval; graph expansion addresses it."""
    hits = indexed_system.vector_index.search(
        "code that holds a database lock while making a network call",
        role="Senior Dev",
        top_k=8,
    )
    doc_ids = [c.doc_id for c, _ in hits]
    assert any("process_jazzcash_callback" in d for d in doc_ids), doc_ids

@pytest.mark.parametrize("role", list(ALLOWED))
def test_chroma_rbac_never_returns_unauthorized(indexed_system: CodebaseIndexer, role: str) -> None:
    """The in-query Chroma filter never returns a chunk above the role's clearance."""
    hits = indexed_system.vector_index.search("signing keys HMAC HSM credentials", role=role, top_k=20)
    for chunk, _ in hits:
        assert chunk.security_level.lower() in ALLOWED[role]


def test_junior_cannot_see_restricted_but_security_lead_can(indexed_system: CodebaseIndexer) -> None:
    junior = indexed_system.vector_index.search("SigningKeyStore HSM signing keys", role="Junior Dev", top_k=20)
    lead = indexed_system.vector_index.search("SigningKeyStore HSM signing keys", role="Security Lead", top_k=20)
    assert not any("secrets" in c.file_path for c, _ in junior)
    assert any("secrets" in c.file_path for c, _ in lead)