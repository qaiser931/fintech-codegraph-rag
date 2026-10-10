"""CLI script to run full codebase indexing (AST, Graph, BM25, Dense Vector)."""

import sys
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.ingestion.indexer import CodebaseIndexer


def main() -> None:
    print("=" * 70)
    print("Executing Master Indexing Pipeline...")
    print("=" * 70)

    stats = CodebaseIndexer().index_codebase()

    print("\n[Indexing Complete! Summary Statistics]")
    print(f"Total Chunks Indexed   : {stats['total_chunks']}")
    print(f"Graph Nodes / Edges    : {stats['graph_nodes']} nodes / {stats['graph_edges']} edges")
    print(f"Vector Dimensions      : {stats['vector_dimension']}")
    print(f"Security Breakdown     : {stats['security_breakdown']}")
    print("\n[Persisted Artifact Paths]")
    for k, v in stats["paths"].items():
        print(f"  - {k}: {v}")
    print("=" * 70)


if __name__ == "__main__":
    main()
