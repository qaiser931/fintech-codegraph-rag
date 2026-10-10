"""Mocked timeout/error regressions; no live generation or model downloads."""

import sys
import time
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
import requests

from ui import api_client


@pytest.fixture
def mocked_post(monkeypatch):
    monkeypatch.setattr(api_client.settings, "api_role_tokens", {})
    post = Mock()
    monkeypatch.setattr(api_client.requests, "post", post)
    return post


def test_slow_response_reports_elapsed_without_retry(monkeypatch, mocked_post):
    clock = [100.0]
    monkeypatch.setattr(time, "monotonic", lambda: clock[0])

    def slow_response(*args, **kwargs):
        clock[0] += 7.0
        raise requests.ReadTimeout("mocked slow response")

    mocked_post.side_effect = slow_response
    with pytest.raises(api_client.UITimeoutError) as captured:
        api_client.query_api(
            "http://127.0.0.1:8001", "Why timeout?", "Senior Dev", None,
            read_timeout=6.0,
        )

    assert captured.value.elapsed_s == 7.0
    assert captured.value.timeout_s == 6.0
    severity, message = api_client.describe_query_error(captured.value)
    assert severity == "warning"
    assert "completion is unknown" in message
    assert "No automatic retry" in message
    assert "API is healthy" not in message
    mocked_post.assert_called_once()


@pytest.mark.parametrize("exception,expected", [
    (requests.ConnectTimeout("private detail"), "Connecting"),
    (requests.ConnectionError("private detail"), "Could not reach"),
])
def test_connection_failures_remain_distinct(mocked_post, exception, expected):
    mocked_post.side_effect = exception
    with pytest.raises(type(exception)) as captured:
        api_client.query_api(
            "http://127.0.0.1:8001", "Why timeout?", "Senior Dev", None,
        )
    severity, message = api_client.describe_query_error(captured.value)
    assert severity == "error"
    assert expected in message
    assert "private detail" not in message
    mocked_post.assert_called_once()


@pytest.mark.parametrize("code,expected", [
    (401, "Authentication failed"),
    (403, "Access denied"),
    (500, "backend failed"),
    (503, "backend failed"),
    (422, "rejected"),
])
def test_http_status_errors_are_classified(mocked_post, code, expected):
    response = requests.Response()
    response.status_code = code
    mocked_post.return_value = response
    with pytest.raises(requests.HTTPError) as captured:
        api_client.query_api(
            "http://127.0.0.1:8001", "Why timeout?", "Senior Dev", None,
        )
    severity, message = api_client.describe_query_error(captured.value)
    assert severity == "error"
    assert expected in message
    assert str(code) in message
    mocked_post.assert_called_once()


def test_configuration_error_does_not_expose_details():
    severity, message = api_client.describe_query_error(
        api_client.UIAuthenticationError("private detail")
    )
    assert severity == "error"
    assert "Authentication configuration" in message
    assert "private detail" not in message


@pytest.mark.parametrize("value", [0, -1, float("inf"), float("nan")])
def test_invalid_query_timeout_never_sends_request(mocked_post, value):
    with pytest.raises(ValueError, match="positive finite"):
        api_client.query_api(
            "http://127.0.0.1:8001", "Why timeout?", "Senior Dev", None,
            read_timeout=value,
        )
    mocked_post.assert_not_called()


def test_connect_timeout_environment_is_configurable(monkeypatch):
    monkeypatch.setenv("CODEGRAPH_CONNECT_TIMEOUT", "3.5")
    assert api_client._timeout_from_env("CODEGRAPH_CONNECT_TIMEOUT", 5) == 3.5
    monkeypatch.setenv("CODEGRAPH_CONNECT_TIMEOUT", "inf")
    with pytest.raises(ValueError, match="positive finite"):
        api_client._timeout_from_env("CODEGRAPH_CONNECT_TIMEOUT", 5)


@pytest.mark.parametrize("slow", [False, True])
def test_ollama_uses_finite_wait_and_closes_without_retry(monkeypatch, slow):
    from src.config import settings
    from src.generation.generator import _call_ollama

    monkeypatch.setattr(settings, "ollama_connect_timeout", 5.0)
    monkeypatch.setattr(settings, "ollama_read_timeout", 180.0)
    close = Mock()
    chat = Mock(return_value={
        "message": {"content": "grounded answer"},
        "prompt_eval_count": 11,
        "eval_count": 7,
    })
    if slow:
        chat.side_effect = httpx.ReadTimeout("mocked slow provider")
    client = SimpleNamespace(chat=chat, _client=SimpleNamespace(close=close))
    factory = Mock(return_value=client)
    monkeypatch.setitem(sys.modules, "ollama", SimpleNamespace(Client=factory))

    if slow:
        with pytest.raises(httpx.ReadTimeout):
            _call_ollama("system", "question", "qwen2.5:1.5b", 0.0, "")
    else:
        assert _call_ollama(
            "system", "question", "qwen2.5:1.5b", 0.0, ""
        ) == ("grounded answer", 11, 7)

    factory.assert_called_once()
    timeout = factory.call_args.kwargs["timeout"]
    assert timeout.connect == 5.0
    assert timeout.read == 180.0
    assert timeout.write == 180.0
    assert timeout.pool == 180.0
    chat.assert_called_once()
    assert chat.call_args.kwargs["model"] == "qwen2.5:1.5b"
    assert chat.call_args.kwargs["options"] == {"temperature": 0.0}
    assert chat.call_args.kwargs["messages"] == [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "question"},
    ]
    close.assert_called_once()
