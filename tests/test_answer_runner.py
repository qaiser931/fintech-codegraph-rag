"""End-to-end runner state checks with synthetic responses and no network."""
import json
from pathlib import Path
import sys

import httpx
import pytest

pytest.importorskip("deepeval")
from scripts import final_answer_evaluation as runner
from src.evaluation import judge as module


@pytest.fixture
def setup(monkeypatch, tmp_path):
    state = {"queries": 0, "source_ok": True, "judge_ok": True}
    corpus = runner.ROOT / "data/sample_codebase"
    case = json.loads((runner.ROOT / "data/evaluation/gold_dataset.json").read_text())[0]
    doc_id = case["expected_symbols"][0]
    path, symbol = doc_id.split("::")

    class Client:
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def post(self, url, **kwargs):
            state["queries"] += 1
            return httpx.Response(200, json={"query": case["question"], "role": "Security Lead",
                "answer": "Synthetic fixture answer", "retrieved_items": [{"doc_id": doc_id}],
                "citations": [{"file_path": path, "symbol_name": symbol}]})
        def get(self, url, **kwargs):
            code = (runner.ROOT / path).read_text().rstrip("\n")
            return httpx.Response(200, json={"code": code if state["source_ok"] else "different source"})

    class Metric:
        score = 0.5
        reason = "Synthetic fixture score, not a real judge result"
        def measure(self, case):
            if not state["judge_ok"]:
                raise ValueError("credential-bearing-failure")
        def is_successful(self):
            return False

    monkeypatch.setattr(httpx, "Client", Client)
    monkeypatch.setattr(runner, "private_key", lambda: "fixture-private-key")
    monkeypatch.setattr(module, "groq_judge", lambda *args: object())
    monkeypatch.setattr(module, "make_metrics", lambda *args: {n: Metric() for n in module.METRIC_NAMES})
    monkeypatch.setattr(sys, "argv", ["runner", "--base-url", "https://fixture.invalid",
                                    "--limit", "1", "--output", str(tmp_path)])
    return state, tmp_path


def test_failed_judge_resumes_saved_answer_without_regeneration(setup, monkeypatch):
    state, directory = setup
    state["judge_ok"] = False
    assert runner.main() == 1
    data = json.loads((directory / "results.json").read_text())
    assert data["cases"][0]["metrics"]["faithfulness"]["score"] is None
    assert "credential-bearing-failure" not in json.dumps(data)
    state["judge_ok"] = True
    monkeypatch.setattr(sys, "argv", sys.argv + ["--resume"])
    assert runner.main() == 0
    assert state["queries"] == 1
    data = json.loads((directory / "results.json").read_text())
    assert data["complete"] and not data["full_dataset_complete"]
    assert runner.main() == 0
    assert state["queries"] == 1


def test_source_verification_failure_retains_answer_for_explicit_resume(setup, monkeypatch):
    state, directory = setup
    state["source_ok"] = False
    assert runner.main() == 1
    data = json.loads((directory / "results.json").read_text())
    assert data["cases"][0]["snapshot"]["response"]["answer"] == "Synthetic fixture answer"
    assert not data["complete"] and not data["cases"][0].get("source_verified")
    state["source_ok"] = True
    monkeypatch.setattr(sys, "argv", sys.argv + ["--resume"])
    assert runner.main() == 0
    assert state["queries"] == 1
