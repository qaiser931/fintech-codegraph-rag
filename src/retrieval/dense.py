"""Dense vector retrieval backed by ChromaDB with pre-retrieval RBAC filtering.

Embeddings come from a real sentence-transformers model (BAAI/bge-small-en-v1.5).
The RBAC clearance filter is applied INSIDE the Chroma query (``where`` clause),
so chunks outside the caller's clearance are never fetched into memory.
"""

import hashlib
import json
import math
import os
import uuid
from abc import ABC, abstractmethod
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

import chromadb  # noqa: E402
import numpy as np  # noqa: E402

from src.config import settings  # noqa: E402
from src.ingestion.chunker import CodeChunk  # noqa: E402
from src.retrieval.bm25 import tokenize_code  # noqa: E402
from src.security.rbac import rbac_manager  # noqa: E402

COLLECTION_NAME = "code_chunks"
BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

_STR_FIELDS = [
    "doc_id", "tenant_id", "version_tag", "timestamp", "security_level",
    "jurisdiction", "source_authority", "file_path", "symbol_name", "symbol_type",
]


class BaseEmbeddingEngine(ABC):
    """Abstract base class for vector embedding engines."""

    @abstractmethod
    def embed_texts(self, texts: List[str]) -> np.ndarray:
        """Generate dense vector embeddings for a list of strings."""

    @abstractmethod
    def embed_query(self, query: str) -> np.ndarray:
        """Generate dense vector embedding for a single query string."""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Vector dimensionality."""


class FastCodeEmbeddingEngine(BaseEmbeddingEngine):
    """Hash-based keyword vectorizer. NOT semantic. Kept only for offline unit tests."""

    def __init__(self, dimension: int = 384) -> None:
        self._dim = dimension

    @property
    def dimension(self) -> int:
        return self._dim

    def _text_to_vector(self, text: str) -> np.ndarray:
        tokens = tokenize_code(text)
        vec = np.zeros(self._dim, dtype=np.float32)
        for idx, tok in enumerate(tokens):
            tok_bytes = tok.encode("utf-8")
            h1 = int(hashlib.md5(tok_bytes).hexdigest(), 16) % self._dim
            h2 = int(hashlib.sha256(tok_bytes).hexdigest(), 16) % self._dim
            weight = 1.0 / math.log2(idx + 3)
            vec[h1] += (1.0 if h1 % 2 == 0 else -1.0) * weight
            vec[h2] += (1.0 if h2 % 2 == 0 else -1.0) * weight * 0.5
        norm = np.linalg.norm(vec)
        return vec / norm if norm > 1e-6 else vec

    def embed_texts(self, texts: List[str]) -> np.ndarray:
        return np.vstack([self._text_to_vector(t) for t in texts])

    def embed_query(self, query: str) -> np.ndarray:
        return self._text_to_vector(query)


class SentenceTransformerEmbeddingEngine(BaseEmbeddingEngine):
    """Neural embedding engine using HuggingFace SentenceTransformers (BGE)."""

    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5") -> None:
        from sentence_transformers import SentenceTransformer

        self.model_name = model_name
        self.model = SentenceTransformer(model_name)
        dim_fn = getattr(self.model, "get_embedding_dimension", None)
        if dim_fn is None:
            dim_fn = self.model.get_sentence_embedding_dimension
        self._dim = int(dim_fn())

    @property
    def dimension(self) -> int:
        return self._dim

    def embed_texts(self, texts: List[str]) -> np.ndarray:
        embs = self.model.encode(
            texts, normalize_embeddings=True, show_progress_bar=False, batch_size=32
        )
        return np.asarray(embs, dtype=np.float32)

    def embed_query(self, query: str) -> np.ndarray:
        prefix = BGE_QUERY_PREFIX if "bge" in self.model_name.lower() else ""
        emb = self.model.encode(
            [prefix + query], normalize_embeddings=True, show_progress_bar=False
        )[0]
        return np.asarray(emb, dtype=np.float32)


@lru_cache(maxsize=1)
def get_embedding_engine() -> BaseEmbeddingEngine:
    """Return the shared real embedding engine. No silent fallback."""
    try:
        return SentenceTransformerEmbeddingEngine(settings.embedding_model)
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            f"Could not load embedding model '{settings.embedding_model}'. "
            "Check internet (first run downloads it) and that sentence-transformers is installed."
        ) from exc


def _chunk_metadata(chunk: CodeChunk) -> Dict[str, Any]:
    """Flat Chroma metadata for a chunk, plus the full chunk as JSON."""
    meta: Dict[str, Any] = {f: str(getattr(chunk, f, "") or "") for f in _STR_FIELDS}
    meta["security_level"] = meta["security_level"].lower()
    meta["start_line"] = int(getattr(chunk, "start_line", 0) or 0)
    meta["end_line"] = int(getattr(chunk, "end_line", 0) or 0)
    meta["chunk_json"] = json.dumps(chunk.model_dump(), default=str)
    return meta


def _chunk_from_metadata(meta: Dict[str, Any]) -> CodeChunk:
    return CodeChunk(**json.loads(meta["chunk_json"]))


class DenseVectorIndex:
    """ChromaDB-backed dense index with in-query RBAC filtering."""

    def __init__(self, embedding_engine: Optional[BaseEmbeddingEngine] = None) -> None:
        self.engine = embedding_engine or get_embedding_engine()
        self.chunks: List[CodeChunk] = []
        self.vectors: Optional[np.ndarray] = None
        self._client: Any = None
        self._collection: Any = None

    @staticmethod
    def _fill(collection: Any, chunks: List[CodeChunk], vectors: np.ndarray) -> None:
        if not chunks:
            return
        collection.add(
            ids=[f"chunk-{i}" for i in range(len(chunks))],
            embeddings=np.asarray(vectors, dtype=np.float32).tolist(),
            documents=[c.search_text for c in chunks],
            metadatas=[_chunk_metadata(c) for c in chunks],
        )

    def _new_ephemeral_collection(self) -> None:
        """(Re)create an in-memory Chroma collection from the stored chunks/vectors."""
        client = chromadb.EphemeralClient()
        collection = client.create_collection(
            name=f"chunks_{uuid.uuid4().hex}", metadata={"hnsw:space": "cosine"}
        )
        if self.vectors is not None:
            self._fill(collection, self.chunks, self.vectors)
        self._client, self._collection = client, collection

    def _ensure_collection(self) -> int:
        """Return the collection size, rebuilding it if Chroma lost it."""
        if self._collection is not None:
            try:
                return int(self._collection.count())
            except Exception:
                pass
        if self.chunks and self.vectors is not None:
            self._new_ephemeral_collection()
            return int(self._collection.count())
        return 0

    def build_index(self, chunks: List[CodeChunk]) -> None:
        """Embed all chunks and load them into an in-memory Chroma collection."""
        self.chunks = list(chunks)
        self.vectors = (
            self.engine.embed_texts([c.search_text for c in self.chunks])
            if self.chunks
            else None
        )
        self._new_ephemeral_collection()

    def search(
        self,
        query: str,
        role: str = "Junior Dev",
        top_k: int = 10,
        tenant_id: Optional[str] = None,
    ) -> List[Tuple[CodeChunk, float]]:
        """Semantic search. The RBAC filter runs inside the Chroma query itself."""
        total = self._ensure_collection()
        if total == 0:
            return []

        clearance = sorted(str(c).lower() for c in rbac_manager.get_clearance_for_role(role))
        if not clearance:
            return []

        where: Dict[str, Any] = {"security_level": {"$in": clearance}}
        if tenant_id:
            where = {"$and": [where, {"tenant_id": {"$eq": tenant_id}}]}

        query_vec = self.engine.embed_query(query)
        result = self._collection.query(
            query_embeddings=[query_vec.tolist()],
            n_results=min(top_k, total),
            where=where,
            include=["metadatas", "distances"],
        )

        hits: List[Tuple[CodeChunk, float]] = []
        for meta, dist in zip(result["metadatas"][0], result["distances"][0]):
            hits.append((_chunk_from_metadata(meta), float(1.0 - dist)))
        return hits

    def save_index(self, directory: Optional[Path] = None) -> Path:
        """Persist the index to a Chroma PersistentClient directory."""
        target = Path(directory or settings.vector_db_path)
        target.mkdir(parents=True, exist_ok=True)
        client = chromadb.PersistentClient(path=str(target))
        try:
            client.delete_collection(COLLECTION_NAME)
        except Exception:
            pass
        collection = client.create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine", "embedding_model": settings.embedding_model},
        )
        if self.vectors is not None:
            self._fill(collection, self.chunks, self.vectors)
        self._client, self._collection = client, collection
        return target

    def load_index(self, directory: Optional[Path] = None) -> None:
        """Open a persisted Chroma index and restore chunks/vectors."""
        target = Path(directory or settings.vector_db_path)
        if not (target / "chroma.sqlite3").exists():
            raise FileNotFoundError(f"Chroma vector index not found at {target}")
        client = chromadb.PersistentClient(path=str(target))
        collection = client.get_collection(COLLECTION_NAME)
        data = collection.get(include=["metadatas", "embeddings"])

        order = sorted(range(len(data["ids"])), key=lambda i: int(data["ids"][i].split("-")[1]))
        self.chunks = [_chunk_from_metadata(data["metadatas"][i]) for i in order]
        self.vectors = (
            np.asarray([data["embeddings"][i] for i in order], dtype=np.float32)
            if order
            else None
        )
        self._client, self._collection = client, collection