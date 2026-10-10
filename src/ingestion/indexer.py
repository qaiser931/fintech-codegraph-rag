"""Unified Indexing Pipeline Coordinator for CodeGraph RAG.

Extracts AST symbol chunks, builds the NetworkX call graph, constructs
the BM25 keyword index, generates dense embeddings, and persists all artifacts.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional
from src.config import settings
from src.ingestion.chunker import CodeChunk, SymbolChunker
from src.ingestion.graph_builder import DependencyGraphBuilder
from src.retrieval.bm25 import BM25SearchEngine
from src.retrieval.dense import DenseVectorIndex, get_embedding_engine


class CodebaseIndexer:
    """Master coordinator orchestrating AST chunking, graph construction, and hybrid indexing."""

    def __init__(self) -> None:
        self.chunker = SymbolChunker()
        self.graph_builder = DependencyGraphBuilder()
        self.bm25_index = BM25SearchEngine()
        self.vector_index = DenseVectorIndex(get_embedding_engine())
        self.chunks: List[CodeChunk] = []

    def index_codebase(
        self,
        codebase_dir: Optional[Path] = None,
        base_dir: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """Execute full indexing pipeline across the target codebase.

        1. AST parsing & symbol-level chunking
        2. NetworkX dependency call graph construction
        3. BM25 keyword index generation
        4. Dense vector embedding generation
        5. Artifact persistence to disk

        Returns:
            Dictionary containing indexing summary statistics.
        """
        target_dir = Path(codebase_dir or settings.sample_codebase_dir)
        root_dir = Path(base_dir or settings.base_dir)

        # Step 1: Symbol chunking
        self.chunks = self.chunker.chunk_directory(target_dir, base_dir=root_dir)

        # Step 2: Build and save dependency graph
        self.graph_builder.build_from_chunks(self.chunks)
        graph_path = self.graph_builder.save_graph(settings.graph_store_path)

        # Step 3: Build and save BM25 index
        self.bm25_index.build_index(self.chunks)
        bm25_path = self.bm25_index.save_index(settings.bm25_store_path)

        # Step 4: Build and save Dense Vector index
        self.vector_index.build_index(self.chunks)
        vector_path = self.vector_index.save_index(settings.vector_db_path)

        # Tally security levels
        sec_counts: Dict[str, int] = {}
        for c in self.chunks:
            sec_counts[c.security_level] = sec_counts.get(c.security_level, 0) + 1

        stats = {
            "total_chunks": len(self.chunks),
            "graph_nodes": self.graph_builder.graph.number_of_nodes(),
            "graph_edges": self.graph_builder.graph.number_of_edges(),
            "security_breakdown": sec_counts,
            "vector_dimension": self.vector_index.engine.dimension,
            "paths": {
                "graph_store": str(graph_path),
                "bm25_store": str(bm25_path),
                "vector_store": str(vector_path),
            },
        }
        return stats

    def load_existing_indices(self) -> None:
        """Load previously saved graph, BM25, and vector indices from disk."""
        self.graph_builder.load_graph(settings.graph_store_path)
        self.bm25_index.load_index(settings.bm25_store_path)
        self.vector_index.load_index(settings.vector_db_path)
        self.chunks = self.bm25_index.chunks


