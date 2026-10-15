"""Regression checks for honest scores, resumability, and corrected legacy labels."""
from types import SimpleNamespace
import json

from scripts.final_answer_evaluation import completed, fingerprint, save_reports
from src.evaluation.judge import METRIC_NAMES, JudgeError, RequestBudget, measure_metric


def record(score=0.5):
    snapshot = {"response": {"answer": "Fixture answer"}, "retrieval_context": ["Fixture code"]}
    return {"id": "Q01", "source_verified": True, "snapshot": snapshot, "snapshot_sha256": fingerprint(snapshot),
            "metrics": {n: {"status": "complete", "score": score} for n in METRIC_NAMES}}


def test_partial_judge_report_never_substitutes_missing_scores(tmp_path):
    value = record()
    value["metrics"]["faithfulness"] = {"status": "failed", "score": None}
    assert not save_reports(tmp_path, {"protocol": "fixture"}, [value], 40)
    data = json.loads((tmp_path / "results.json").read_text())
    assert not data["full_dataset_complete"]
    assert data["summary"]["faithfulness"] == {"scored_cases": 0, "mean": None}
    assert data["summary"]["reference_correctness"]["mean"] == 0.5


def test_completed_subset_is_not_a_full_dataset_benchmark(tmp_path):
    assert save_reports(tmp_path, {}, [record()], 1)
    assert not json.loads((tmp_path / "results.json").read_text())["full_dataset_complete"]


def test_modified_snapshot_cannot_be_reused_as_completed():
    value = record()
    assert completed(value)
    value["snapshot"]["response"]["answer"] = "Changed answer"
    assert not completed(value)


def test_metric_failure_does_not_expose_provider_text_or_assign_zero():
    class Broken:
        def measure(self, case):
            raise ValueError("credential-bearing-provider-response")
    result = measure_metric(Broken(), None)
    assert result["status"] == "failed" and result["score"] is None
    assert "credential-bearing" not in json.dumps(result)


def test_budget_prevents_automatic_extra_requests():
    import pytest
    budget = RequestBudget(requests=1, seconds=60)
    budget.take()
    with pytest.raises(JudgeError):
        budget.take()


def test_legacy_model_evaluation_requires_explicit_opt_in(monkeypatch):
    from src.evaluation.llm_evaluation import _score_with_optional_model
    monkeypatch.delenv("CODEGRAPH_JUDGE_MODEL", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "fixture")
    assert _score_with_optional_model(None, "answer", ["code"]) == (None, "proxy")


def test_legacy_correctness_is_not_relevancy_or_one_minus_faithfulness(monkeypatch):
    from src.evaluation.llm_evaluation import _score_with_optional_model
    import src.evaluation.judge as module
    monkeypatch.setenv("CODEGRAPH_JUDGE_MODEL", "fixture")
    monkeypatch.setenv("GROQ_API_KEY", "fixture")
    result = {"complete": True, "metrics": {
        "faithfulness": {"score": 0.9}, "answer_relevancy": {"score": 0.2},
        "reference_correctness": {"score": 0.6}, "hallucination_free": {"score": 0.7}}}
    monkeypatch.setattr(module, "evaluate_answer", lambda *args: result)
    case = SimpleNamespace(question="question", answer_facts=["fact"])
    scores, backend = _score_with_optional_model(case, "answer", ["code"])
    assert backend == "deepeval"
    assert scores["answer_correctness"] == 0.6
    assert abs(scores["hallucination_rate"] - 0.3) < 1e-9
