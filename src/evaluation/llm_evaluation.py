"""
LLM evaluation for Codebase Graph RAG.

Evaluates generated answers against the gold dataset using deterministic
fact-grounding checks. This module is intentionally independent from the
retrieval benchmark so retrieval metrics remain unchanged.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Sequence

from src.evaluation.runner import EvaluationCase, load_gold_dataset
from src.generation.generator import CodeRAGGenerator
from src.retrieval.hybrid import HybridRetriever


PROJECT_ROOT = Path(__file__).resolve().parents[2]

GOLD_PATH = (
    PROJECT_ROOT
    / "data"
    / "evaluation"
    / "gold_dataset.json"
)

RESULTS_PATH = (
    PROJECT_ROOT
    / "data"
    / "evaluation"
    / "llm_results.json"
)

REPORT_PATH = (
    PROJECT_ROOT
    / "data"
    / "evaluation"
    / "llm_report.md"
)


@dataclass
class LLMEvaluationResult:
    """Evaluation result for one generated answer."""

    case_id: str
    faithfulness: float
    answer_correctness: float
    hallucination_rate: float
    citation_count: int
    answer: str
    evaluation_backend: str = "proxy"


def _normalise(text: str) -> str:
    """Normalize text for deterministic phrase matching."""
    text = text.lower()
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _fact_matches_answer(
    fact: str,
    answer: str,
) -> bool:
    """
    Determine whether a gold fact is reasonably represented in the answer.

    Matching is intentionally conservative:
    - exact normalized phrase
    - or all meaningful words from the fact appear in the answer
    """
    fact_normalized = _normalise(fact)
    answer_normalized = _normalise(answer)

    if not fact_normalized:
        return False

    if fact_normalized in answer_normalized:
        return True

    words = [
        word
        for word in re.findall(
            r"[a-zA-Z0-9_]+",
            fact_normalized,
        )
        if len(word) > 3
    ]

    if not words:
        return False

    matched = sum(
        1
        for word in words
        if word in answer_normalized
    )

    return (
        matched / len(words)
    ) >= 0.75


def _calculate_answer_correctness(
    answer: str,
    gold_facts: Sequence[str],
) -> float:
    """Measure how many gold answer facts are represented."""
    if not gold_facts:
        return 0.0

    matched = sum(
        1
        for fact in gold_facts
        if _fact_matches_answer(
            fact,
            answer,
        )
    )

    return matched / len(gold_facts)


def _calculate_faithfulness(
    answer: str,
    retrieved_context: Sequence[str],
) -> float:
    """
    Estimate faithfulness using retrieved-context phrase grounding.

    Each factual sentence is checked for overlap with retrieved evidence.
    This is a deterministic proxy; Ragas/DeepEval can provide the
    model-based metric later.
    """
    if not answer.strip():
        return 0.0

    context = _normalise(
        " ".join(retrieved_context)
    )

    if not context:
        return 0.0

    sentences = [
        sentence.strip()
        for sentence in re.split(
            r"[.!?]\s+",
            answer,
        )
        if sentence.strip()
    ]

    if not sentences:
        return 0.0

    grounded = 0

    for sentence in sentences:
        normalized_sentence = _normalise(
            sentence
        )

        words = [
            word
            for word in re.findall(
                r"[a-zA-Z0-9_]+",
                normalized_sentence,
            )
            if len(word) > 3
        ]

        if not words:
            continue

        matched = sum(
            1
            for word in words
            if word in context
        )

        if (
            matched / len(words)
        ) >= 0.50:
            grounded += 1

    return grounded / len(sentences)


def _calculate_hallucination_rate(
    faithfulness: float,
) -> float:
    """Convert faithfulness proxy into a hallucination-rate proxy."""
    return max(
        0.0,
        min(
            1.0,
            1.0 - faithfulness,
        ),
    )


def _score_with_optional_model(
    case: EvaluationCase,
    answer: str,
    retrieved_context: Sequence[str],
) -> tuple[dict[str, float] | None, str]:
    """Use an explicitly configured judge; never relabel relevancy as correctness.

    The default legacy runner remains a clearly labelled proxy. Merely installing
    an SDK does not authorize live requests. The final fail-closed benchmark is
    scripts/final_answer_evaluation.py and never substitutes these proxies.
    """
    model = os.environ.get("CODEGRAPH_JUDGE_MODEL", "").strip()
    key = os.environ.get("GROQ_API_KEY", "").strip()
    if not model or not key or not answer.strip() or not retrieved_context:
        return None, "proxy"
    try:
        from src.evaluation.judge import evaluate_answer
        result = evaluate_answer(case.question, answer, list(retrieved_context),
                                 case.answer_facts, model, key)
        if result["complete"]:
            metrics = result["metrics"]
            return {
                "faithfulness": metrics["faithfulness"]["score"],
                "answer_correctness": metrics["reference_correctness"]["score"],
                "hallucination_rate": 1.0 - metrics["hallucination_free"]["score"],
            }, "deepeval"
    except Exception:
        pass
    return None, "proxy"


def _retrieved_context(
    result: Any,
) -> List[str]:
    """Extract textual evidence from retrieved chunks."""
    context: List[str] = []

    for item in result.items:
        chunk = item.chunk

        parts = [
            str(chunk.symbol_name or ""),
            str(chunk.file_path or ""),
            str(chunk.start_line or ""),
            str(chunk.end_line or ""),
        ]

        content = getattr(
            chunk,
            "content",
            None,
        )

        if content:
            parts.append(
                str(content)
            )

        text = " ".join(
            part
            for part in parts
            if part
        )

        if text:
            context.append(text)

    return context


def evaluate_case(
    generator: CodeRAGGenerator,
    case: EvaluationCase,
) -> LLMEvaluationResult:
    """Generate and evaluate one gold question."""

    generated = generator.generate(
        query=case.question,
        role="Senior Dev",
        retrieval_kwargs={
            "top_k": 6,
            "use_graph": True,
            "use_reranker": True,
            "seed_count": 3,
            "hops": 2,
            "max_graph_nodes": 6,
        },
    )

    answer = generated.answer

    context = _retrieved_context(
        generated.retrieval_result
    )

    faithfulness = _calculate_faithfulness(
        answer,
        context,
    )

    answer_correctness = _calculate_answer_correctness(
        answer,
        case.answer_facts,
    )

    hallucination_rate = _calculate_hallucination_rate(
        faithfulness
    )

    model_scores, evaluation_backend = _score_with_optional_model(
        case,
        answer,
        context,
    )

    if model_scores is not None:
        faithfulness = model_scores.get(
            "faithfulness",
            faithfulness,
        )
        answer_correctness = model_scores.get(
            "answer_correctness",
            answer_correctness,
        )
        hallucination_rate = model_scores.get(
            "hallucination_rate",
            hallucination_rate,
        )

    return LLMEvaluationResult(
        case_id=case.case_id,
        faithfulness=faithfulness,
        answer_correctness=answer_correctness,
        hallucination_rate=hallucination_rate,
        citation_count=len(
            generated.citations
        ),
        answer=answer,
        evaluation_backend=evaluation_backend,
    )


def aggregate_results(
    results: Sequence[LLMEvaluationResult],
) -> dict[str, float]:
    """Calculate macro-average LLM evaluation metrics."""

    if not results:
        return {
            "faithfulness": 0.0,
            "answer_correctness": 0.0,
            "hallucination_rate": 0.0,
        }

    count = len(results)

    return {
        "faithfulness": (
            sum(
                result.faithfulness
                for result in results
            )
            / count
        ),
        "answer_correctness": (
            sum(
                result.answer_correctness
                for result in results
            )
            / count
        ),
        "hallucination_rate": (
            sum(
                result.hallucination_rate
                for result in results
            )
            / count
        ),
    }


def save_results(
    results: Sequence[LLMEvaluationResult],
) -> None:
    """Save detailed LLM evaluation results."""

    payload = {
        "summary": aggregate_results(
            results
        ),
        "cases": [
            {
                "case_id": result.case_id,
                "faithfulness": result.faithfulness,
                "answer_correctness": result.answer_correctness,
                "hallucination_rate": result.hallucination_rate,
                "citation_count": result.citation_count,
                "evaluation_backend": result.evaluation_backend,
                "answer": result.answer,
            }
            for result in results
        ],
    }

    RESULTS_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    RESULTS_PATH.write_text(
        json.dumps(
            payload,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def save_report(
    results: Sequence[LLMEvaluationResult],
) -> None:
    """Save Markdown LLM evaluation report."""

    summary = aggregate_results(
        results
    )

    lines = [
        "# Codebase Graph RAG LLM Evaluation",
        "",
        "Legacy answer evaluation; each case records its backend. See the final answer runner for fail-closed model scores.",
        "",
        "| Metric | Score |",
        "| --- | ---: |",
        f"| Faithfulness | {summary['faithfulness']:.4f} |",
        f"| Answer Correctness | {summary['answer_correctness']:.4f} |",
        f"| Hallucination Rate | {summary['hallucination_rate']:.4f} |",
        "",
        "## Method",
        "",
        "- Faithfulness is estimated from overlap between generated answers and retrieved evidence.",
        "- Answer correctness is estimated against the gold `answer_facts`.",
        "- The proxy hallucination rate is `1 - proxy faithfulness`; DeepEval violation rate is 1 minus its separate hallucination-free score (not 1 minus faithfulness).",
        "",
        f"Evaluation backend used: {('deepeval' if any(result.evaluation_backend == 'deepeval' for result in results) else 'proxy')}",
        "",
        "Model judging requires explicit CODEGRAPH_JUDGE_MODEL and GROQ_API_KEY. Reference correctness uses G-Eval against gold facts; answer relevancy is not correctness. This legacy runner labels fallback cases as proxy; final_answer_evaluation.py instead preserves failed metrics as unscored.",
    ]

    REPORT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    REPORT_PATH.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )


def save_combined_report(
    retrieval_results: dict[str, dict[str, float]],
    llm_results: Sequence[LLMEvaluationResult],
    *,
    path: str | Path | None = None,
) -> None:
    """Merge retrieval benchmark metrics with answer-quality metrics."""

    if path is None:
        path = PROJECT_ROOT / "data" / "evaluation" / "combined_report.md"

    output_path = Path(path)
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    llm_summary = aggregate_results(
        llm_results
    )

    lines = [
        "# Phase 8 Combined Evaluation Report",
        "",
        "## Deterministic retrieval results",
        "",
    ]

    if retrieval_results:
        metric_names = list(
            next(iter(retrieval_results.values())).keys()
        )
        lines.extend(
            [
                "| Mode | " + " | ".join(metric_names) + " |",
                "| --- | " + " | ".join("---:" for _ in metric_names) + " |",
            ]
        )

        for mode_name, metrics in retrieval_results.items():
            values = [f"{metrics.get(metric, 0.0):.4f}" for metric in metric_names]
            lines.append(f"| {mode_name} | {' | '.join(values)} |")
    else:
        lines.append("No deterministic retrieval results were available.")

    lines.extend(
        [
            "",
            "## LLM answer-quality proxies",
            "",
            "| Metric | Score |",
            "| --- | ---: |",
            f"| Faithfulness | {llm_summary['faithfulness']:.4f} |",
            f"| Answer Correctness | {llm_summary['answer_correctness']:.4f} |",
            f"| Hallucination Rate | {llm_summary['hallucination_rate']:.4f} |",
            "",
            "The deterministic benchmark and the answer-quality proxy metrics are tracked separately and can be read together in this report.",
        ]
    )

    output_path.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )


def main(*, max_cases: int | None = 5) -> None:
    """Run the LLM evaluation.

    By default this executes a small smoke subset to avoid full 40-question
    generation runs unless the caller explicitly asks for the full dataset.
    """

    print("=" * 72)
    print("Phase 8 - LLM Answer Evaluation")
    print("=" * 72)

    cases = load_gold_dataset(
        GOLD_PATH
    )

    if max_cases is None:
        selected_cases = cases
        print(
            f"Loaded gold questions: {len(cases)} (full run requested)"
        )
    else:
        selected_cases = cases[:max_cases]
        print(
            f"Loaded gold questions: {len(cases)}; evaluating a smoke subset of {len(selected_cases)} cases"
        )

    from src.ingestion.indexer import CodebaseIndexer
    indexer = CodebaseIndexer()
    indexer.load_existing_indices()

    retriever = HybridRetriever(
        indexer
    )

    generator = CodeRAGGenerator(
        retriever
    )

    results: List[LLMEvaluationResult] = []

    for index, case in enumerate(
        selected_cases,
        start=1,
    ):
        print(
            f"[{index:02d}/{len(selected_cases)}] "
            f"{case.case_id}"
        )

        result = evaluate_case(
            generator,
            case,
        )

        results.append(
            result
        )

    summary = aggregate_results(
        results
    )

    print("\nRESULTS")
    print("=" * 72)

    for metric, value in summary.items():
        print(
            f"{metric}: {value:.4f}"
        )

    save_results(
        results
    )

    save_report(
        results
    )

    combined_path = PROJECT_ROOT / "data" / "evaluation" / "combined_report.md"
    real_results_path = PROJECT_ROOT / "data" / "evaluation" / "real_results.json"

    if real_results_path.exists():
        try:
            with real_results_path.open("r", encoding="utf-8") as handle:
                retrieval_results = json.load(handle)
            save_combined_report(
                retrieval_results,
                results,
                path=combined_path,
            )
            print(
                f"  Combined report: {combined_path}"
            )
        except Exception:
            pass

    print("\nSaved:")
    print(
        f"  Results: {RESULTS_PATH}"
    )
    print(
        f"  Report:  {REPORT_PATH}"
    )


if __name__ == "__main__":
    main()