"""
Deterministic evaluation metrics for the Codebase Graph RAG system.

These metrics intentionally avoid LLM calls so retrieval and graph quality
can be measured reproducibly in offline tests.
"""

from __future__ import annotations

import math
from typing import Any, Iterable, Sequence


def _normalise(value: Any) -> str:
    """Convert a value to a stable comparison string."""
    return str(value).strip().lower()


def _unique(values: Iterable[Any]) -> list[str]:
    """Return normalized unique values while preserving order."""
    result: list[str] = []
    seen: set[str] = set()

    for value in values:
        normalized = _normalise(value)

        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)

    return result


def _top_k(values: Sequence[Any], k: int) -> list[Any]:
    """Return the first k retrieved values."""
    if k <= 0:
        return []

    return list(values[:k])


def recall_at_k(
    retrieved: Sequence[Any],
    relevant: Sequence[Any],
    k: int = 5,
) -> float:
    """
    Calculate Recall@K.

    Recall@K = relevant items retrieved in top K / total relevant items.
    """
    relevant_set = set(_unique(relevant))

    if not relevant_set:
        return 0.0

    retrieved_set = set(
        _unique(
            _top_k(
                retrieved,
                k,
            )
        )
    )

    return len(retrieved_set & relevant_set) / len(relevant_set)


def precision_at_k(
    retrieved: Sequence[Any],
    relevant: Sequence[Any],
    k: int = 5,
) -> float:
    """
    Calculate Precision@K.

    Precision@K = relevant items in top K / K.
    """
    if k <= 0:
        return 0.0

    relevant_set = set(_unique(relevant))
    top = _top_k(retrieved, k)

    if not top:
        return 0.0

    hits = sum(
        1
        for item in top
        if _normalise(item) in relevant_set
    )

    return hits / len(top)


def mean_reciprocal_rank(
    retrieved: Sequence[Any],
    relevant: Sequence[Any],
) -> float:
    """
    Calculate MRR for a single query.

    The reciprocal rank is 1/rank of the first relevant result.
    """
    relevant_set = set(_unique(relevant))

    if not relevant_set:
        return 0.0

    for rank, item in enumerate(
        retrieved,
        start=1,
    ):
        if _normalise(item) in relevant_set:
            return 1.0 / rank

    return 0.0


def ndcg_at_k(
    retrieved: Sequence[Any],
    relevant: Sequence[Any],
    k: int = 5,
) -> float:
    """
    Calculate binary-relevance NDCG@K.

    A retrieved item is either relevant (1) or not relevant (0).
    """
    if k <= 0:
        return 0.0

    relevant_set = set(_unique(relevant))
    top = _top_k(retrieved, k)

    if not relevant_set:
        return 0.0

    dcg = 0.0

    for rank, item in enumerate(
        top,
        start=1,
    ):
        if _normalise(item) in relevant_set:
            dcg += 1.0 / math.log2(rank + 1)

    ideal_hits = min(
        len(relevant_set),
        k,
    )

    idcg = sum(
        1.0 / math.log2(rank + 1)
        for rank in range(
            1,
            ideal_hits + 1,
        )
    )

    if idcg == 0.0:
        return 0.0

    return dcg / idcg


def code_symbol_resolution_precision(
    retrieved_symbols: Sequence[str],
    expected_symbols: Sequence[str],
) -> float:
    """
    Measure how accurately retrieved code symbols resolve to gold symbols.
    """
    retrieved = _unique(retrieved_symbols)
    expected = set(_unique(expected_symbols))

    if not retrieved:
        return 0.0

    hits = sum(
        1
        for symbol in retrieved
        if symbol in expected
    )

    return hits / len(retrieved)


def call_path_recall_at_k(
    retrieved_path: Sequence[str],
    expected_path: Sequence[str],
    k: int | None = None,
) -> float:
    """
    Measure how much of the expected call path appears in the retrieved path.

    Order is not required here; execution-path correctness is handled
    separately by execution_path_accuracy().
    """
    expected = _unique(expected_path)

    if not expected:
        return 0.0

    if k is None:
        retrieved = _unique(retrieved_path)
    else:
        retrieved = _unique(
            _top_k(
                retrieved_path,
                k,
            )
        )

    retrieved_set = set(retrieved)

    hits = sum(
        1
        for symbol in expected
        if symbol in retrieved_set
    )

    return hits / len(expected)


def _is_ordered_subsequence(
    retrieved_path: Sequence[str],
    expected_path: Sequence[str],
) -> bool:
    """
    Return True when expected_path appears inside retrieved_path
    in the same order.

    Extra symbols are allowed between expected symbols.

    Example:

        Retrieved:
            A -> X -> B -> Y -> C -> Z -> D -> E

        Expected:
            A -> B -> C -> D -> E

        Result:
            True
    """
    retrieved = [
        _normalise(item)
        for item in retrieved_path
    ]

    expected = [
        _normalise(item)
        for item in expected_path
    ]

    if not retrieved or not expected:
        return False

    expected_index = 0

    for symbol in retrieved:
        if symbol == expected[expected_index]:
            expected_index += 1

            if expected_index == len(expected):
                return True

    return False


def execution_path_accuracy(
    retrieved_path: Sequence[str]
    | Sequence[Sequence[str]],
    expected_path: Sequence[str],
) -> float:
    """
    Return 1 when any discovered execution path contains the complete
    expected path in the correct order.

    Unlike exact path matching, this metric allows legitimate intermediate
    implementation calls that are not part of the gold root-cause path.

    Supports both:

        ["a", "b", "c"]

    and:

        [
            ["a", "x", "b", "y", "c"],
            ["a", "d", "c"],
        ]
    """
    if not retrieved_path or not expected_path:
        return 0.0

    first_item = retrieved_path[0]

    if isinstance(first_item, str):
        candidates: Sequence[Sequence[str]] = [
            retrieved_path  # type: ignore[list-item]
        ]
    else:
        candidates = retrieved_path  # type: ignore[assignment]

    for path in candidates:
        if _is_ordered_subsequence(
            path,
            expected_path,
        ):
            return 1.0

    return 0.0


def citation_groundedness(
    citations: Sequence[Any],
    expected_files: Sequence[str],
    expected_symbols: Sequence[str] | None = None,
) -> float:
    """
    Estimate citation groundedness against the gold file/symbol set.

    A citation may be:
      - a string containing a file path/symbol,
      - a dictionary with file_path/path and optionally symbol/symbol_name.

    A citation receives credit when it references an expected file or symbol.
    """
    if not citations:
        return 0.0

    expected_files_set = {
        _normalise(path)
        for path in expected_files
    }

    expected_symbols_set = {
        _normalise(symbol)
        for symbol in (
            expected_symbols or []
        )
    }

    grounded = 0

    for citation in citations:
        file_path = ""
        symbol = ""
        raw = ""

        if isinstance(citation, dict):
            file_path = _normalise(
                citation.get("file_path")
                or citation.get("path")
                or ""
            )

            symbol = _normalise(
                citation.get("symbol")
                or citation.get("symbol_name")
                or ""
            )

            raw = _normalise(citation)

        else:
            raw = _normalise(citation)

        if (
            file_path in expected_files_set
            or symbol in expected_symbols_set
            or any(
                path in raw
                for path in expected_files_set
            )
            or any(
                sym in raw
                for sym in expected_symbols_set
            )
        ):
            grounded += 1

    return grounded / len(citations)


def evaluate_retrieval_case(
    *,
    retrieved_symbols: Sequence[str],
    expected_symbols: Sequence[str],
    retrieved_call_path: Sequence[str] | None = None,
    retrieved_execution_paths: Sequence[Sequence[str]] | None = None,
    expected_call_path: Sequence[str] | None = None,
    citations: Sequence[Any] | None = None,
    expected_files: Sequence[str] | None = None,
    k: int = 5,
) -> dict[str, float]:
    """
    Calculate all deterministic metrics for one evaluation case.

    `retrieved_call_path` is used for call-path recall.

    `retrieved_execution_paths` contains all execution paths discovered
    by graph expansion and is used for execution-path accuracy.
    """
    expected_path = expected_call_path or []
    retrieved_path = retrieved_call_path or []

    execution_paths: (
        Sequence[str]
        | Sequence[Sequence[str]]
    )

    if retrieved_execution_paths:
        execution_paths = retrieved_execution_paths
    else:
        execution_paths = retrieved_path

    return {
        "recall_at_k": recall_at_k(
            retrieved_symbols,
            expected_symbols,
            k=k,
        ),
        "precision_at_k": precision_at_k(
            retrieved_symbols,
            expected_symbols,
            k=k,
        ),
        "mrr": mean_reciprocal_rank(
            retrieved_symbols,
            expected_symbols,
        ),
        "ndcg_at_k": ndcg_at_k(
            retrieved_symbols,
            expected_symbols,
            k=k,
        ),
        "code_symbol_resolution_precision": (
            code_symbol_resolution_precision(
                retrieved_symbols,
                expected_symbols,
            )
        ),
        "call_path_recall_at_k": call_path_recall_at_k(
            retrieved_path,
            expected_path,
            k=k,
        ),
        "execution_path_accuracy": execution_path_accuracy(
            execution_paths,
            expected_path,
        ),
        "citation_groundedness": citation_groundedness(
            citations or [],
            expected_files or [],
            expected_symbols,
        ),
    }


def aggregate_metrics(
    results: Sequence[dict[str, float]],
) -> dict[str, float]:
    """
    Calculate macro averages across evaluation cases.
    """
    if not results:
        return {}

    metric_names = results[0].keys()

    return {
        metric: (
            sum(
                float(
                    row.get(
                        metric,
                        0.0,
                    )
                )
                for row in results
            )
            / len(results)
        )
        for metric in metric_names
    }