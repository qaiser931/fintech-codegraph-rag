"""Demo: hybrid retrieval + graph expansion for the JazzCash timeout scenario."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import settings  # noqa: E402
from src.ingestion.indexer import CodebaseIndexer  # noqa: E402
from src.retrieval.hybrid import HybridRetriever  # noqa: E402

QUERY = "Why does the JazzCash payment callback handler throw a timeout error during peak traffic?"


def main() -> None:
    indexer = CodebaseIndexer()
    indexer.index_codebase(settings.sample_codebase_dir, base_dir=settings.base_dir)
    retriever = HybridRetriever(indexer)
    graph = retriever.graph

    for role in ["Junior Dev", "Senior Dev", "Security Lead"]:
        result = retriever.retrieve(QUERY, role=role)
        print("=" * 78)
        print(f"ROLE: {role}")
        print(f"QUERY: {QUERY}")
        print("-" * 78)
        for i, item in enumerate(result.items, start=1):
            score = "-" if item.rerank_score is None else f"{item.rerank_score:.3f}"
            c = item.chunk
            extra = f" hop={item.hop} via {item.direction}" if item.source == "graph" else ""
            print(f"{i:>2}. [{item.source:<6}] rerank={score:>6} {c.file_path}:{c.start_line}-{c.end_line} {c.symbol_name}{extra}")
        print("\nExecution paths:")
        if not result.execution_paths:
            print("  (none)")
        for path in result.execution_paths:
            print("  " + " -> ".join(graph.nodes[n]["symbol_name"] for n in path))
        print("\nTimings (ms):", result.timings_ms)


if __name__ == "__main__":
    main()