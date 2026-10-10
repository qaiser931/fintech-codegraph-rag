"""
Evaluation runner for Codebase Graph RAG.

The runner evaluates retrieval outputs against the 40-question gold dataset.
It supports three retrieval configurations:

1. vector_only
2. hybrid
3. hybrid_graph

The runner is deterministic and does not make LLM calls.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from src.evaluation.metrics import (
    aggregate_metrics,
    evaluate_retrieval_case,
)


@dataclass(frozen=True)
class EvaluationCase:
    """One gold evaluation question."""

    case_id: str
    question: str
    expected_symbols: list[str]
    expected_files: list[str]
    expected_call_path: list[str]
    answer_facts: list[str]


@dataclass
class RetrievalOutput:
    """Retrieval result for one evaluation question."""

    retrieved_symbols: list[str]
    retrieved_call_path: list[str] = field(default_factory=list)
    retrieved_execution_paths: list[list[str]] = field(default_factory=list)
    citations: list[Any] = field(default_factory=list)


def load_gold_dataset(path: str | Path) -> list[EvaluationCase]:
    """
    Load the gold dataset from JSON.

    The dataset must contain a list of evaluation cases.
    """
    dataset_path = Path(path)

    if not dataset_path.exists():
        raise FileNotFoundError(
            f"Gold dataset not found: {dataset_path}"
        )

    with dataset_path.open(
        "r",
        encoding="utf-8",
    ) as handle:
        raw_data = json.load(handle)

    if not isinstance(raw_data, list):
        raise ValueError(
            "Gold dataset must contain a JSON list."
        )

    cases: list[EvaluationCase] = []

    for item in raw_data:
        cases.append(
            EvaluationCase(
                case_id=str(item["id"]),
                question=str(item["question"]),
                expected_symbols=list(
                    item.get(
                        "expected_symbols",
                        [],
                    )
                ),
                expected_files=list(
                    item.get(
                        "expected_files",
                        [],
                    )
                ),
                expected_call_path=list(
                    item.get(
                        "expected_call_path",
                        [],
                    )
                ),
                answer_facts=list(
                    item.get(
                        "answer_facts",
                        [],
                    )
                ),
            )
        )

    return cases


def evaluate_case(
    case: EvaluationCase,
    output: RetrievalOutput,
    *,
    k: int = 5,
) -> dict[str, float]:
    """Evaluate one retrieval output against one gold case."""

    return evaluate_retrieval_case(
        retrieved_symbols=output.retrieved_symbols,
        expected_symbols=case.expected_symbols,
        retrieved_call_path=output.retrieved_call_path,
        retrieved_execution_paths=output.retrieved_execution_paths,
        expected_call_path=case.expected_call_path,
        citations=output.citations,
        expected_files=case.expected_files,
        k=k,
    )


def evaluate_mode(
    cases: Sequence[EvaluationCase],
    outputs: Sequence[RetrievalOutput],
    *,
    k: int = 5,
) -> dict[str, float]:
    """
    Evaluate one retrieval mode across all gold cases.

    `cases` and `outputs` must have the same length and corresponding order.
    """
    if len(cases) != len(outputs):
        raise ValueError(
            "Number of evaluation cases must match number of outputs."
        )

    results = [
        evaluate_case(
            case,
            output,
            k=k,
        )
        for case, output in zip(
            cases,
            outputs,
        )
    ]

    return aggregate_metrics(results)


def evaluate_all_modes(
    cases: Sequence[EvaluationCase],
    mode_outputs: dict[str, Sequence[RetrievalOutput]],
    *,
    k: int = 5,
) -> dict[str, dict[str, float]]:
    """
    Evaluate vector-only, hybrid, and hybrid-graph modes.

    Returns:
        {
            "vector_only": {...},
            "hybrid": {...},
            "hybrid_graph": {...}
        }
    """
    results: dict[str, dict[str, float]] = {}

    for mode_name, outputs in mode_outputs.items():
        results[mode_name] = evaluate_mode(
            cases,
            outputs,
            k=k,
        )

    return results


def save_results(
    results: dict[str, dict[str, float]],
    path: str | Path,
) -> None:
    """Save evaluation results as formatted JSON."""

    output_path = Path(path)

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with output_path.open(
        "w",
        encoding="utf-8",
    ) as handle:
        json.dump(
            results,
            handle,
            indent=2,
            ensure_ascii=False,
        )


def build_markdown_report(
    results: dict[str, dict[str, float]],
    *,
    title: str = "Codebase Graph RAG Evaluation",
) -> str:
    """Build a Markdown comparison table from evaluation results."""

    if not results:
        return (
            f"# {title}\n\n"
            "No evaluation results available.\n"
        )

    metric_names = list(
        next(
            iter(results.values())
        ).keys()
    )

    lines = [
        f"# {title}",
        "",
        "| Metric | "
        + " | ".join(results.keys())
        + " |",
        "| --- | "
        + " | ".join(
            "---:" for _ in results
        )
        + " |",
    ]

    for metric in metric_names:
        values = []

        for mode in results:
            value = results[mode].get(
                metric,
                0.0,
            )

            values.append(
                f"{value:.4f}"
            )

        lines.append(
            f"| {metric} | "
            + " | ".join(values)
            + " |"
        )

    lines.extend(
        [
            "",
            "## Evaluation modes",
            "",
            "- **vector_only**: dense/vector retrieval without hybrid lexical retrieval or graph expansion.",
            "- **hybrid**: dense + BM25 retrieval combined through the existing hybrid pipeline.",
            "- **hybrid_graph**: hybrid retrieval followed by code dependency graph expansion.",
            "",
            "These metrics are deterministic retrieval/graph metrics. "
            "LLM-based faithfulness and answer-correctness evaluation "
            "should be reported separately.",
        ]
    )

    return "\n".join(lines)


def save_markdown_report(
    results: dict[str, dict[str, float]],
    path: str | Path,
    *,
    title: str = "Codebase Graph RAG Evaluation",
) -> None:
    """Save a Markdown evaluation report."""

    output_path = Path(path)

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    report = build_markdown_report(
        results,
        title=title,
    )

    output_path.write_text(
        report,
        encoding="utf-8",
    )