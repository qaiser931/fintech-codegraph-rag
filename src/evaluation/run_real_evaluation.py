"""Run the real Phase 8 retrieval benchmark against the indexed codebase."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from src.evaluation.runner import (
    EvaluationCase,
    RetrievalOutput,
    evaluate_all_modes,
    load_gold_dataset,
    save_markdown_report,
    save_results,
)
from src.ingestion.indexer import CodebaseIndexer
from src.retrieval.hybrid import HybridRetriever


PROJECT_ROOT = Path(__file__).resolve().parents[2]

GOLD_PATH = PROJECT_ROOT / "data" / "evaluation" / "gold_dataset.json"
RESULTS_PATH = PROJECT_ROOT / "data" / "evaluation" / "real_results.json"
REPORT_PATH = PROJECT_ROOT / "data" / "evaluation" / "real_report.md"


def _load_cases() -> List[EvaluationCase]:
    """Load the 40-question gold evaluation dataset."""
    return load_gold_dataset(GOLD_PATH)


def _build_citations(items: List[Any]) -> List[Dict[str, Any]]:
    """
    Convert retrieved chunks into citation metadata.

    Each citation preserves the exact source information needed for
    citation-groundedness evaluation:
      - file path
      - line range
      - symbol name
      - symbol type
      - document id
      - retrieval source
    """
    citations: List[Dict[str, Any]] = []

    for item in items:
        chunk = item.chunk

        citations.append(
            {
                "doc_id": chunk.doc_id,
                "file_path": chunk.file_path,
                "start_line": chunk.start_line,
                "end_line": chunk.end_line,
                "symbol_name": chunk.symbol_name,
                "symbol_type": chunk.symbol_type,
                "source": item.source,
            }
        )

    return citations


def _run_vector_only(
    retriever: HybridRetriever,
    query: str,
    role: str,
    top_k: int,
) -> RetrievalOutput:
    """Run the true dense-vector-only baseline."""

    hits = retriever.indexer.vector_index.search(
        query,
        role=role,
        top_k=top_k,
    )

    symbols = [
        chunk.doc_id
        for chunk, _score in hits
    ]

    citations = [
        {
            "doc_id": chunk.doc_id,
            "file_path": chunk.file_path,
            "start_line": chunk.start_line,
            "end_line": chunk.end_line,
            "symbol_name": chunk.symbol_name,
            "symbol_type": chunk.symbol_type,
            "source": "vector",
        }
        for chunk, _score in hits
    ]

    return RetrievalOutput(
        retrieved_symbols=symbols,
        retrieved_call_path=[],
        retrieved_execution_paths=[],
        citations=citations,
    )


def _run_hybrid(
    retriever: HybridRetriever,
    query: str,
    role: str,
    top_k: int,
) -> RetrievalOutput:
    """Run dense + BM25 + RRF + cross-encoder reranking."""

    result = retriever.retrieve(
        query=query,
        role=role,
        top_k=top_k,
        use_graph=False,
        use_reranker=True,
    )

    symbols = [
        item.chunk.doc_id
        for item in result.items
    ]

    citations = _build_citations(
        result.items
    )

    return RetrievalOutput(
        retrieved_symbols=symbols,
        retrieved_call_path=[],
        retrieved_execution_paths=[],
        citations=citations,
    )


def _run_hybrid_graph(
    retriever: HybridRetriever,
    query: str,
    role: str,
    top_k: int,
) -> RetrievalOutput:
    """
    Run the complete hybrid + graph retrieval pipeline.

    Gold expected_call_path is intentionally not used during retrieval.
    """

    result = retriever.retrieve(
        query=query,
        role=role,
        top_k=top_k,
        use_graph=True,
        use_reranker=True,
        seed_count=3,
        hops=2,
        max_graph_nodes=6,
    )

    symbols = [
        item.chunk.doc_id
        for item in result.items
    ]

    citations = _build_citations(
        result.items
    )

    execution_paths = result.execution_paths or []

    selected_path: List[str] = []

    if execution_paths:
        selected_path = list(
            max(
                execution_paths,
                key=lambda path: (
                    len(path),
                    tuple(
                        str(symbol)
                        for symbol in path
                    ),
                ),
            )
        )

    return RetrievalOutput(
        retrieved_symbols=symbols,
        retrieved_call_path=selected_path,
        retrieved_execution_paths=[
            list(path)
            for path in execution_paths
        ],
        citations=citations,
    )


def _print_q40_diagnostic(
    case: EvaluationCase,
    output: RetrievalOutput,
) -> None:
    """Print detailed execution-path information for Q40."""

    if case.case_id != "Q40":
        return

    print("\n")
    print("=" * 72)
    print("Q40 EXECUTION PATH DIAGNOSTIC")
    print("=" * 72)

    print("\nExpected execution/call path:")
    for index, symbol in enumerate(
        case.expected_call_path,
        start=1,
    ):
        print(
            f"  {index}. {symbol}"
        )

    print("\nSelected retrieved call path:")
    if output.retrieved_call_path:
        for index, symbol in enumerate(
            output.retrieved_call_path,
            start=1,
        ):
            print(
                f"  {index}. {symbol}"
            )
    else:
        print("  <empty>")

    print(
        "\nAll discovered execution paths:"
    )

    if not output.retrieved_execution_paths:
        print("  <none>")
    else:
        for path_index, path in enumerate(
            output.retrieved_execution_paths,
            start=1,
        ):
            print(
                f"\n  Path {path_index}:"
            )

            for symbol_index, symbol in enumerate(
                path,
                start=1,
            ):
                print(
                    f"    {symbol_index}. {symbol}"
                )

    print("\nRetrieved symbols:")
    if output.retrieved_symbols:
        for index, symbol in enumerate(
            output.retrieved_symbols,
            start=1,
        ):
            print(
                f"  {index}. {symbol}"
            )
    else:
        print("  <empty>")

    print(
        "\n" + "=" * 72
    )
    print("END Q40 DIAGNOSTIC")
    print("=" * 72)
    print()


def _build_outputs(
    cases: List[EvaluationCase],
    retriever: HybridRetriever,
) -> Dict[str, List[RetrievalOutput]]:
    """Run all three retrieval modes for every gold question."""

    outputs: Dict[str, List[RetrievalOutput]] = {
        "vector_only": [],
        "hybrid": [],
        "hybrid_graph": [],
    }

    for index, case in enumerate(
        cases,
        start=1,
    ):
        print(
            f"[{index:02d}/{len(cases)}] "
            f"{case.case_id}: {case.question}"
        )

        role = "Senior Dev"

        outputs["vector_only"].append(
            _run_vector_only(
                retriever,
                case.question,
                role,
                top_k=6,
            )
        )

        outputs["hybrid"].append(
            _run_hybrid(
                retriever,
                case.question,
                role,
                top_k=6,
            )
        )

        hybrid_graph_output = _run_hybrid_graph(
            retriever,
            case.question,
            role,
            top_k=6,
        )

        outputs["hybrid_graph"].append(
            hybrid_graph_output
        )

        _print_q40_diagnostic(
            case,
            hybrid_graph_output,
        )

    return outputs


def main() -> None:
    """Run the complete Phase 8 retrieval benchmark."""

    print("=" * 72)
    print("Phase 8 - Real Retrieval Evaluation")
    print("=" * 72)

    cases = _load_cases()

    print(
        f"Loaded gold questions: {len(cases)}"
    )

    indexer = CodebaseIndexer()

    indexer.load_existing_indices()

    print(
        f"Loaded indexed chunks: {len(indexer.chunks)}"
    )

    print(
        "Loaded graph nodes: "
        f"{indexer.graph_builder.graph.number_of_nodes()}"
    )

    print(
        "Loaded graph edges: "
        f"{indexer.graph_builder.graph.number_of_edges()}"
    )

    retriever = HybridRetriever(indexer)

    outputs = _build_outputs(
        cases,
        retriever,
    )

    print(
        "\nCalculating metrics..."
    )

    results = evaluate_all_modes(
        cases,
        outputs,
        k=5,
    )

    save_results(
        results,
        RESULTS_PATH,
    )

    save_markdown_report(
        results,
        REPORT_PATH,
    )

    print(
        "\n" + "=" * 72
    )

    print("RESULTS")

    print("=" * 72)

    for mode, metrics in results.items():
        print(
            f"\n--- {mode} ---"
        )

        for metric_name, value in metrics.items():
            print(
                f"{metric_name}: {value:.4f}"
            )

    print("\nSaved:")

    print(
        f"  Results: {RESULTS_PATH}"
    )

    print(
        f"  Report:  {REPORT_PATH}"
    )


if __name__ == "__main__":
    main()