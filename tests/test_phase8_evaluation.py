from src.evaluation.metrics import (
    aggregate_metrics,
    call_path_recall_at_k,
    citation_groundedness,
    code_symbol_resolution_precision,
    execution_path_accuracy,
    mean_reciprocal_rank,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
)


def test_recall_at_k():
    retrieved = ["A", "B", "C", "D"]
    relevant = ["B", "D", "E"]

    assert recall_at_k(retrieved, relevant, k=4) == 2 / 3


def test_precision_at_k():
    retrieved = ["A", "B", "C", "D"]
    relevant = ["B", "D"]

    assert precision_at_k(retrieved, relevant, k=4) == 0.5


def test_mrr():
    retrieved = ["A", "B", "C"]
    relevant = ["B"]

    assert mean_reciprocal_rank(retrieved, relevant) == 0.5


def test_ndcg():
    retrieved = ["A", "B", "C"]
    relevant = ["B"]

    assert 0.0 < ndcg_at_k(retrieved, relevant, k=3) < 1.0


def test_code_symbol_resolution_precision():
    retrieved = [
        "src.services.payment.PaymentService.process_callback",
        "src.fake.Unknown.symbol",
    ]
    expected = [
        "src.services.payment.PaymentService.process_callback",
    ]

    assert code_symbol_resolution_precision(retrieved, expected) == 0.5


def test_call_path_recall():
    retrieved = [
        "handle_jazzcash_callback",
        "process_callback",
        "lock_payment_row",
    ]
    expected = [
        "handle_jazzcash_callback",
        "process_callback",
        "lock_payment_row",
        "send_payment",
    ]

    assert call_path_recall_at_k(retrieved, expected) == 0.75


def test_execution_path_accuracy():
    expected = [
        "handle_jazzcash_callback",
        "process_callback",
        "lock_payment_row",
        "send_payment",
    ]

    assert execution_path_accuracy(expected, expected) == 1.0

    wrong_order = [
        "handle_jazzcash_callback",
        "lock_payment_row",
        "process_callback",
        "send_payment",
    ]

    assert execution_path_accuracy(wrong_order, expected) == 0.0


def test_citation_groundedness():
    citations = [
        {
            "file_path": "src/services/payment.py",
            "symbol": "src.services.payment.PaymentService.process_callback",
        },
        {
            "file_path": "src/fake.py",
            "symbol": "src.fake.Unknown.symbol",
        },
    ]

    expected_files = [
        "src/services/payment.py",
    ]

    expected_symbols = [
        "src.services.payment.PaymentService.process_callback",
    ]

    assert citation_groundedness(
        citations,
        expected_files,
        expected_symbols,
    ) == 0.5


def test_aggregate_metrics():
    rows = [
        {
            "recall_at_k": 1.0,
            "precision_at_k": 0.5,
        },
        {
            "recall_at_k": 0.5,
            "precision_at_k": 1.0,
        },
    ]

    result = aggregate_metrics(rows)

    assert result["recall_at_k"] == 0.75
    assert result["precision_at_k"] == 0.75
from pathlib import Path

from src.evaluation.runner import (
    RetrievalOutput,
    build_markdown_report,
    evaluate_all_modes,
    evaluate_mode,
    load_gold_dataset,
    save_markdown_report,
    save_results,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GOLD_DATASET = PROJECT_ROOT / "data" / "evaluation" / "gold_dataset.json"


def test_load_gold_dataset():
    cases = load_gold_dataset(GOLD_DATASET)

    assert len(cases) == 40
    assert cases[0].case_id == "Q01"
    assert cases[-1].case_id == "Q40"


def test_evaluate_mode():
    cases = load_gold_dataset(GOLD_DATASET)

    outputs = [
        RetrievalOutput(
            retrieved_symbols=case.expected_symbols,
            retrieved_call_path=case.expected_call_path,
            citations=case.expected_files,
        )
        for case in cases
    ]

    results = evaluate_mode(cases, outputs)

    assert results["recall_at_k"] > 0.0
    assert results["mrr"] > 0.0
    assert results["execution_path_accuracy"] == 1.0


def test_evaluate_all_modes():
    cases = load_gold_dataset(GOLD_DATASET)

    perfect_outputs = [
        RetrievalOutput(
            retrieved_symbols=case.expected_symbols,
            retrieved_call_path=case.expected_call_path,
            citations=case.expected_files,
        )
        for case in cases
    ]

    weak_outputs = [
        RetrievalOutput(
            retrieved_symbols=[],
            retrieved_call_path=[],
            citations=[],
        )
        for _ in cases
    ]

    results = evaluate_all_modes(
        cases,
        {
            "vector_only": weak_outputs,
            "hybrid": perfect_outputs,
            "hybrid_graph": perfect_outputs,
        },
    )

    assert set(results) == {
        "vector_only",
        "hybrid",
        "hybrid_graph",
    }

    assert (
        results["hybrid"]["recall_at_k"]
        > results["vector_only"]["recall_at_k"]
    )


def test_markdown_report():
    results = {
        "vector_only": {
            "recall_at_k": 0.5,
            "mrr": 0.4,
        },
        "hybrid": {
            "recall_at_k": 0.7,
            "mrr": 0.6,
        },
        "hybrid_graph": {
            "recall_at_k": 0.9,
            "mrr": 0.8,
        },
    }

    report = build_markdown_report(results)

    assert "# Codebase Graph RAG Evaluation" in report
    assert "vector_only" in report
    assert "hybrid" in report
    assert "hybrid_graph" in report
    assert "recall_at_k" in report


def test_save_results_and_report():
    import tempfile

    with tempfile.TemporaryDirectory(
        dir=PROJECT_ROOT / "data" / "evaluation"
    ) as temp_dir:
        temp_path = Path(temp_dir)

        results = {
            "vector_only": {
                "recall_at_k": 0.5,
            },
            "hybrid": {
                "recall_at_k": 0.7,
            },
            "hybrid_graph": {
                "recall_at_k": 0.9,
            },
        }

        json_path = temp_path / "results.json"
        report_path = temp_path / "report.md"

        save_results(results, json_path)
        save_markdown_report(results, report_path)

        assert json_path.exists()
        assert report_path.exists()
        assert "hybrid_graph" in report_path.read_text(
            encoding="utf-8"
        )