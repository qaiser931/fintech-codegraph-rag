"""Cross-encoder reranker (ms-marco MiniLM)."""

from functools import lru_cache
from typing import List, Optional, Tuple

from src.config import settings
from src.ingestion.chunker import CodeChunk

DEFAULT_RERANKER = "cross-encoder/ms-marco-MiniLM-L-6-v2"
MAX_CHARS = 2000


def _rerank_text(chunk: CodeChunk) -> str:
    return (chunk.search_text or chunk.content)[:MAX_CHARS]


class CrossEncoderReranker:
    """Scores (query, chunk) pairs with a real cross-encoder model."""

    def __init__(self, model_name: Optional[str] = None) -> None:
        from sentence_transformers import CrossEncoder

        self.model_name = model_name or getattr(settings, "reranker_model", DEFAULT_RERANKER)
        self.model = CrossEncoder(self.model_name)

    def score(self, query: str, chunks: List[CodeChunk]) -> List[float]:
        """Return one relevance score per chunk (higher is better)."""
        if not chunks:
            return []
        pairs = [(query, _rerank_text(c)) for c in chunks]
        scores = self.model.predict(pairs, show_progress_bar=False)
        return [float(s) for s in scores]

    def rerank(
        self, query: str, chunks: List[CodeChunk], top_k: Optional[int] = None
    ) -> List[Tuple[CodeChunk, float]]:
        scored = list(zip(chunks, self.score(query, chunks)))
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored[:top_k] if top_k else scored


@lru_cache(maxsize=1)
def get_reranker() -> CrossEncoderReranker:
    """Shared reranker instance. No silent fallback: a load failure raises."""
    try:
        return CrossEncoderReranker()
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "Could not load the cross-encoder reranker. Check internet "
            "(first run downloads it) and that sentence-transformers is installed."
        ) from exc