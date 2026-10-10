"""Exercise real Streamlit reruns with mocked API traffic."""
from pathlib import Path
from unittest.mock import Mock

import pytest
import requests
from streamlit.testing.v1 import AppTest

from ui import api_client

APP = Path(__file__).resolve().parents[1] / "ui" / "app.py"


def evidence():
    return {"role": "Senior Dev", "latency_ms": 25, "sources": [
        {"doc_id": "payment", "symbol_name": "payment", "file_path": "services/payment.py",
         "start_line": 1, "end_line": 3, "source": "graph"}],
        "retrieved_items": [{"doc_id": "payment", "source": "graph"}],
        "call_path": ["callback → payment"]}


def click(at, label):
    next(button for button in at.button if button.label == label).click().run()
    assert not at.exception


@pytest.fixture
def screen(monkeypatch):
    retrieve = Mock(return_value=evidence())
    generate = Mock(return_value={"role": "Senior Dev", "answer": "Mock answer", "status": "SUPPORTED",
                                  "citations": [], "retrieved_items": [], "call_path": []})
    source = Mock(return_value="CONFIDENTIAL SOURCE FOR SENIOR")
    monkeypatch.setattr(api_client, "retrieve_api", retrieve)
    monkeypatch.setattr(api_client, "query_api", generate)
    monkeypatch.setattr(api_client, "fetch_source", source)
    at = AppTest.from_file(str(APP), default_timeout=10).run()
    assert not at.exception
    at.selectbox[0].set_value("Senior Dev").run()
    return at, retrieve, generate, source


def test_explore_renders_evidence_and_opens_source_without_generation(screen):
    at, retrieve, generate, source = screen
    assert at.radio[0].value == "Explore code"
    click(at, "🔍 Explore code")
    retrieve.assert_called_once()
    generate.assert_not_called()
    assert [metric.label for metric in at.metric] == ["Retrieval latency", "Code matches", "Call paths"]
    assert any("Source references" in x.value for x in at.markdown)
    click(at, "Open source")
    source.assert_called_once_with(at.text_input[0].value, "services/payment.py", "Senior Dev")
    assert any("CONFIDENTIAL SOURCE" in code.value for code in at.code)


@pytest.mark.parametrize("change", ["role", "api", "mode"])
def test_scope_change_removes_previous_result_and_source(screen, change):
    at, *_ = screen
    click(at, "🔍 Explore code")
    click(at, "Open source")
    if change == "role":
        at.selectbox[0].set_value("Junior Dev").run()
    elif change == "api":
        at.text_input[0].set_value("http://127.0.0.1:9000").run()
    else:
        at.radio[0].set_value("Generate answer").run()
    assert not at.exception
    with pytest.raises(KeyError):
        at.session_state["last_result"]
    with pytest.raises(KeyError):
        at.session_state["source-1-services/payment.py-1"]
    assert not any("CONFIDENTIAL SOURCE" in code.value for code in at.code)


def test_generate_answer_flow_is_preserved(screen):
    at, retrieve, generate, _ = screen
    at.radio[0].set_value("Generate answer").run()
    click(at, "🚀 Generate answer")
    generate.assert_called_once()
    retrieve.assert_not_called()
    assert any(x.value == "Mock answer" for x in at.markdown)
    assert any(metric.label == "Total Tokens" for metric in at.metric)


def test_old_backend_shows_update_message_and_hides_stale_result(screen):
    at, retrieve, *_ = screen
    click(at, "🔍 Explore code")
    response = requests.Response()
    response.status_code = 404
    retrieve.side_effect = requests.HTTPError(response=response)
    click(at, "🔍 Explore code")
    assert any("Update the backend" in error.value for error in at.error)
    with pytest.raises(KeyError):
        at.session_state["last_result"]


def test_retrieval_client_sends_credentials_and_single_bounded_request(monkeypatch):
    monkeypatch.setattr(api_client.settings, "api_role_tokens", {"private-token": "Senior Dev"})
    response = Mock()
    response.json.return_value = evidence()
    post = Mock(return_value=response)
    monkeypatch.setattr(api_client.requests, "post", post)
    assert api_client.retrieve_api("https://api.example.test/", "Why?", "Senior Dev", "trace") == evidence()
    assert post.call_args.args == ("https://api.example.test/retrieve",)
    assert post.call_args.kwargs["headers"] == {"Authorization": "Bearer private-token"}
    assert post.call_args.kwargs["timeout"] == (5.0, 60.0)
    assert "private-token" not in str(post.call_args.kwargs["json"])
    post.reset_mock()
    post.side_effect = requests.ReadTimeout()
    with pytest.raises(api_client.UITimeoutError):
        api_client.retrieve_api("https://api.example.test", "Why?", "Senior Dev", None)
    assert post.call_count == 1


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf")])
def test_retrieval_client_rejects_invalid_waits_before_network(monkeypatch, value):
    post = Mock()
    monkeypatch.setattr(api_client.requests, "post", post)
    with pytest.raises(ValueError):
        api_client.retrieve_api("http://127.0.0.1:8001", "Why?", "Junior Dev", None, read_timeout=value)
    post.assert_not_called()
