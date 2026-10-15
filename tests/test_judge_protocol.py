"""Use the pinned real SDK with mocked Groq transport; never make live calls."""
import json
import httpx
import pytest
from pydantic import BaseModel

pytest.importorskip("deepeval")
from src.evaluation.judge import JudgeError, RequestBudget, groq_judge, make_metrics


class FixtureSchema(BaseModel):
    facts: list[str]


def mock_client(monkeypatch, payload, status=200):
    class Client:
        def __init__(self, *args, **kwargs):
            assert kwargs["follow_redirects"] is False
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def post(self, url, **kwargs):
            assert url == "https://api.groq.com/openai/v1/chat/completions"
            assert kwargs["json"]["response_format"] == {"type": "json_object"}
            return httpx.Response(status, json=payload)
    monkeypatch.setattr(httpx, "Client", Client)


def test_real_sdk_constructs_four_distinct_metrics():
    judge = groq_judge("fixture-model", "fixture-private-key", RequestBudget())
    metrics = make_metrics(judge)
    assert len({type(m) for m in metrics.values()}) == 4
    assert metrics["reference_correctness"].name == "Reference Correctness"
    assert metrics["hallucination_free"].threshold == 0.7


def test_valid_structured_judge_response_is_parsed_without_retry(monkeypatch):
    mock_client(monkeypatch, {"choices": [{"finish_reason": "stop",
        "message": {"content": '{"facts":["verified fixture"]}'}}]})
    budget = RequestBudget(requests=1)
    judge = groq_judge("fixture", "fixture-private-key", budget)
    assert judge.generate("Fixture prompt", FixtureSchema).facts == ["verified fixture"]
    assert budget.requests == 1


@pytest.mark.parametrize("reason", ["length", "content_filter", None])
def test_truncated_or_incomplete_judge_response_stays_unscored(monkeypatch, reason):
    mock_client(monkeypatch, {"choices": [{"finish_reason": reason,
        "message": {"content": '{"facts":["incomplete"]}'}}]})
    judge = groq_judge("fixture", "fixture-private-key", RequestBudget())
    with pytest.raises(JudgeError):
        judge.generate("Fixture prompt", FixtureSchema)


def test_rate_limit_error_never_exposes_body_or_retries(monkeypatch):
    mock_client(monkeypatch, {"error": "fixture-private-key"}, status=429)
    budget = RequestBudget()
    judge = groq_judge("fixture", "fixture-private-key", budget)
    with pytest.raises(JudgeError) as error:
        judge.generate("Fixture prompt", FixtureSchema)
    assert str(error.value) == "Judge HTTP 429"
    assert budget.requests == 1


def test_all_four_real_sdk_metrics_complete_with_structured_fixture_responses(monkeypatch):
    from src.evaluation.judge import evaluate_answer
    class Client:
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def post(self, url, **kwargs):
            system = kwargs["json"]["messages"][0]["content"]
            if "Match this JSON schema: " in system:
                schema = json.loads(system.split("Match this JSON schema: ", 1)[1])
                fields = set(schema["properties"])
            else:
                fields = {"score", "reason"}
            if fields == {"truths"}:
                value = {"truths": ["Peak latency is 2-6 seconds."]}
            elif fields == {"claims"}:
                value = {"claims": ["Peak latency is 2-6 seconds."]}
            elif fields == {"statements"}:
                value = {"statements": ["Peak latency is 2-6 seconds."]}
            elif fields == {"verdicts"}:
                value = {"verdicts": [{"verdict": "yes", "reason": "Fixture agrees with supplied evidence."}]}
            elif fields == {"reason"}:
                value = {"reason": "Fixture agrees with supplied evidence."}
            elif fields == {"score", "reason"}:
                value = {"score": 10, "reason": "Fixture matches the expected fact."}
            else:
                raise AssertionError("Unexpected real SDK schema fields: " + repr(fields))
            return httpx.Response(200, json={"choices": [{"finish_reason": "stop",
                "message": {"content": json.dumps(value)}}]})
    monkeypatch.setattr(httpx, "Client", Client)
    result = evaluate_answer("What is peak latency?", "Peak latency is 2-6 seconds.",
        ["Peak latency is 2-6 seconds."], ["Peak latency is 2-6 seconds."],
        "fixture", "fixture-private-key")
    assert result["complete"], result
    assert all(m["score"] == 1.0 for m in result["metrics"].values())
