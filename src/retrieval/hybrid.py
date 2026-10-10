"""Hybrid retrieval: dense + BM25 -> RRF -> cross-encoder rerank -> RBAC-aware graph expansion."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from src.ingestion.chunker import CodeChunk
from src.retrieval.graph_expand import expand_call_graph, find_execution_paths
from src.retrieval.reranker import CrossEncoderReranker, get_reranker
from src.retrieval.rrf import reciprocal_rank_fusion
from src.security.rbac import rbac_manager

if TYPE_CHECKING:
    from src.ingestion.indexer import CodebaseIndexer


def _ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 2)


@dataclass
class RetrievedChunk:
    chunk: CodeChunk
    source: str  # "hybrid" (dense/BM25 pipeline) or "graph" (call-graph expansion)
    rrf_score: float = 0.0
    rerank_score: Optional[float] = None
    dense_rank: Optional[int] = None
    bm25_rank: Optional[int] = None
    hop: int = 0
    via: Optional[str] = None
    direction: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        c = self.chunk
        return {
            "doc_id": c.doc_id,
            "symbol_name": c.symbol_name,
            "symbol_type": c.symbol_type,
            "file_path": c.file_path,
            "start_line": c.start_line,
            "end_line": c.end_line,
            "security_level": c.security_level,
            "source": self.source,
            "rrf_score": self.rrf_score,
            "rerank_score": self.rerank_score,
            "dense_rank": self.dense_rank,
            "bm25_rank": self.bm25_rank,
            "hop": self.hop,
            "via": self.via,
            "direction": self.direction,
        }


@dataclass
class RetrievalResult:
    query: str
    role: str
    items: List[RetrievedChunk]
    execution_paths: List[List[str]] = field(default_factory=list)
    candidates: Dict[str, List[str]] = field(default_factory=dict)
    timings_ms: Dict[str, float] = field(default_factory=dict)
    seeds: List[str] = field(default_factory=list)

    @property
    def doc_ids(self) -> List[str]:
        return [i.chunk.doc_id for i in self.items]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "role": self.role,
            "items": [i.to_dict() for i in self.items],
            "execution_paths": self.execution_paths,
            "candidates": self.candidates,
            "timings_ms": self.timings_ms,
            "seeds": self.seeds,
        }


class HybridRetriever:
    """Coordinates the full retrieval pipeline on top of a CodebaseIndexer."""

    def __init__(
        self,
        indexer: "CodebaseIndexer",
        reranker: Optional[CrossEncoderReranker] = None,
        rrf_k: int = 60,
    ) -> None:
        self.indexer = indexer
        self._reranker = reranker
        self.rrf_k = rrf_k
        self._map: Dict[str, CodeChunk] = {}
        self._map_size = -1

    @property
    def reranker(self) -> CrossEncoderReranker:
        if self._reranker is None:
            self._reranker = get_reranker()
        return self._reranker

    @property
    def graph(self):
        return self.indexer.graph_builder.graph

    def _chunk_map(self) -> Dict[str, CodeChunk]:
        chunks = self.indexer.chunks
        if len(chunks) != self._map_size:
            self._map = {c.doc_id: c for c in chunks}
            self._map_size = len(chunks)
        return self._map

    def retrieve(
        self,
        query: str,
        role: str = "Junior Dev",
        top_k: int = 6,
        candidate_k: int = 20,
        rerank_pool: int = 15,
        use_graph: bool = True,
        seed_count: int = 3,
        hops: int = 2,
        max_graph_nodes: int = 6,
        use_reranker: bool = True,
        tenant_id: Optional[str] = None,
    ) -> RetrievalResult:
        """Run the full pipeline. Raises ValueError for an unknown role."""
        started = time.perf_counter()
        rbac_manager.get_clearance_for_role(role)  # fail fast on unknown roles
        timings: Dict[str, float] = {}

        # 1. Dense + BM25, both filtered by role BEFORE ranking
        t = time.perf_counter()
        dense_hits = self.indexer.vector_index.search(
            query, role=role, top_k=candidate_k, tenant_id=tenant_id
        )
        timings["dense_ms"] = _ms(t)

        t = time.perf_counter()
        bm25_hits = self.indexer.bm25_index.search(
            query, role=role, top_k=candidate_k, tenant_id=tenant_id
        )
        timings["bm25_ms"] = _ms(t)

        pool: Dict[str, CodeChunk] = {}
        dense_ids: List[str] = []
        bm25_ids: List[str] = []
        for chunk, _ in dense_hits:
            if rbac_manager.is_chunk_authorized(chunk, role):
                pool[chunk.doc_id] = chunk
                dense_ids.append(chunk.doc_id)
        for chunk, _ in bm25_hits:
            if rbac_manager.is_chunk_authorized(chunk, role):
                pool[chunk.doc_id] = chunk
                bm25_ids.append(chunk.doc_id)

        # 2. Reciprocal Rank Fusion
        t = time.perf_counter()
        fused = reciprocal_rank_fusion({"dense": dense_ids, "bm25": bm25_ids}, k=self.rrf_k)
        timings["rrf_ms"] = _ms(t)
        fused_scores = dict(fused)
        pool_ids = [d for d, _ in fused[:rerank_pool]]
        dense_rank = {d: i for i, d in enumerate(dense_ids, start=1)}
        bm25_rank = {d: i for i, d in enumerate(bm25_ids, start=1)}

        # 3. Cross-encoder rerank
        t = time.perf_counter()
        pool_chunks = [pool[d] for d in pool_ids]
        if use_reranker and pool_chunks:
            scores: List[Optional[float]] = list(self.reranker.score(query, pool_chunks))
        else:
            scores = [None] * len(pool_chunks)
        timings["rerank_ms"] = _ms(t)

        items = [
            RetrievedChunk(
                chunk=pool[d],
                source="hybrid",
                rrf_score=fused_scores[d],
                rerank_score=s,
                dense_rank=dense_rank.get(d),
                bm25_rank=bm25_rank.get(d),
            )
            for d, s in zip(pool_ids, scores)
        ]
        if use_reranker:
            items.sort(key=lambda it: (-(it.rerank_score or 0.0), -it.rrf_score, it.chunk.doc_id))
        top = items[:top_k]

        # 4. RBAC-aware call-graph expansion around the best non-class seeds
        graph_items: List[RetrievedChunk] = []
        seeds: List[str] = []
        t = time.perf_counter()
        if use_graph:
            seeds = [it.chunk.doc_id for it in top if it.chunk.symbol_type != "class"][:seed_count]
            expanded = expand_call_graph(self.graph, seeds, role, hops=hops)
            existing = {it.chunk.doc_id for it in top}
            chunk_map = self._chunk_map()

            found = []
            for node in expanded:
                chunk = chunk_map.get(node.doc_id)
                if chunk is None or node.doc_id in existing or chunk.symbol_type == "class":
                    continue
                if not rbac_manager.is_chunk_authorized(chunk, role):
                    continue
                found.append((node, chunk))

            if found:
                if use_reranker:
                    g_scores: List[Optional[float]] = list(
                        self.reranker.score(query, [c for _, c in found])
                    )
                else:
                    g_scores = [None] * len(found)
                ranked = sorted(
                    zip(found, g_scores),
                    key=lambda x: (x[0][0].hop, -(x[1] or 0.0), x[0][1].doc_id),
                )
                for (node, chunk), s in ranked[:max_graph_nodes]:
                    graph_items.append(
                        RetrievedChunk(
                            chunk=chunk,
                            source="graph",
                            rerank_score=s,
                            hop=node.hop,
                            via=node.via,
                            direction=node.direction,
                        )
                    )
        timings["graph_ms"] = _ms(t)

        final = top + graph_items
        paths: List[List[str]] = []
        if use_graph:
            paths = find_execution_paths(
    self.graph,
    [i.chunk.doc_id for i in final],
    role,
    root_ids=seeds,
)

        timings["total_ms"] = _ms(started)
        return RetrievalResult(
            query=query,
            role=role,
            items=final,
            execution_paths=paths,
            candidates={"dense": dense_ids, "bm25": bm25_ids, "fused": pool_ids},
            timings_ms=timings,
            seeds=seeds,
        )