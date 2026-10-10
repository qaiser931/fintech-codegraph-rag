"""BM25 Keyword and Symbol Search Engine with Pre-Retrieval RBAC Filtering.

Specialized for exact code symbols, method names, decorator routes,
and fintech error strings using custom code tokenization and rank_bm25.
"""

import pickle
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from rank_bm25 import BM25Okapi
from src.config import settings
from src.ingestion.chunker import CodeChunk
from src.security.rbac import rbac_manager


def tokenize_code(text: str) -> List[str]:
    """Tokenize code text splitting CamelCase, snake_case, and preserving exact symbols.

    Args:
        text: Raw source code, docstring, or query string.

    Returns:
        List of normalized lowercase tokens.
    """
    # 1. Extract alphanumeric tokens and symbol identifiers
    raw_tokens = re.findall(r"[A-Za-z0-9_]+", text)
    tokens: List[str] = []

    for tok in raw_tokens:
        tok_lower = tok.lower()
        tokens.append(tok_lower)

        # 2. Split snake_case identifiers
        if "_" in tok:
            subparts = [p.lower() for p in tok.split("_") if p]
            tokens.extend(subparts)

        # 3. Split CamelCase identifiers
        camel_parts = re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z][a-z]|\d|\W|$)|\d+", tok)
        if len(camel_parts) > 1:
            tokens.extend([p.lower() for p in camel_parts])

    return tokens


class BM25SearchEngine:
    """In-memory BM25 index supporting exact symbol lookup, code search, and pre-retrieval RBAC filtering."""

    def __init__(self) -> None:
        self.chunks: List[CodeChunk] = []
        self.tokenized_corpus: List[List[str]] = []
        self.bm25: Optional[BM25Okapi] = None

    def build_index(self, chunks: List[CodeChunk]) -> None:
        """Build BM25 index across all provided chunks."""
        self.chunks = chunks
        self.tokenized_corpus = [tokenize_code(chunk.search_text) for chunk in chunks]
        self.bm25 = BM25Okapi(self.tokenized_corpus)

    def search(
        self,
        query: str,
        role: str = "Junior Dev",
        top_k: int = 10,
        tenant_id: Optional[str] = None,
    ) -> List[Tuple[CodeChunk, float]]:
        """Execute BM25 search with strict PRE-RETRIEVAL RBAC filtering.

        Restricted chunks are filtered out before ranking to prevent unauthorized
        in-memory leakage.

        Args:
            query: User search query or symbol name.
            role: Requesting user's role ("Junior Dev", "Senior Dev", "Security Lead").
            top_k: Maximum number of results to return.
            tenant_id: Optional tenant isolation filter.

        Returns:
            List of (CodeChunk, bm25_score) tuples sorted descending by score.
        """
        if not self.bm25 or not self.chunks:
            return []

        clearance = rbac_manager.get_clearance_for_role(role)
        query_tokens = tokenize_code(query)
        if not query_tokens:
            return []

        # Step 1: Pre-retrieval candidate filtering by RBAC and tenant
        candidate_indices = []
        for idx, chunk in enumerate(self.chunks):
            if chunk.security_level.lower() not in clearance:
                continue
            if tenant_id and chunk.tenant_id != tenant_id:
                continue
            candidate_indices.append(idx)

        if not candidate_indices:
            return []

        # Step 2: Compute BM25 scores across all documents
        raw_scores = self.bm25.get_scores(query_tokens)

        # Step 3: Extract and rank only authorized candidates
        scored_candidates: List[Tuple[CodeChunk, float]] = []
        for idx in candidate_indices:
            score = float(raw_scores[idx])
            if score > 0.0:
                scored_candidates.append((self.chunks[idx], score))

        # Sort descending by BM25 score
        scored_candidates.sort(key=lambda item: item[1], reverse=True)
        return scored_candidates[:top_k]

    def save_index(self, file_path: Optional[Path] = None) -> Path:
        """Persist BM25 index and chunk metadata to disk."""
        target_path = Path(file_path or settings.bm25_store_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "chunks": [c.model_dump() for c in self.chunks],
            "tokenized_corpus": self.tokenized_corpus,
        }
        with open(target_path, "wb") as f:
            pickle.dump(data, f)

        return target_path

    def load_index(self, file_path: Optional[Path] = None) -> None:
        """Load BM25 index from disk."""
        target_path = Path(file_path or settings.bm25_store_path)
        if not target_path.exists():
            raise FileNotFoundError(f"BM25 index not found at {target_path}")

        with open(target_path, "rb") as f:
            data = pickle.load(f)

        self.chunks = [CodeChunk(**d) for d in data["chunks"]]
        self.tokenized_corpus = data["tokenized_corpus"]
        self.bm25 = BM25Okapi(self.tokenized_corpus)
