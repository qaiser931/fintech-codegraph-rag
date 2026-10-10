from __future__ import annotations

from unittest.mock import Mock, patch

import pytest
import requests

from ui import api_client
from ui.api_client import UITimeoutError


def test_role_selects_its_configured_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        api_client.settings,
        "api_role_tokens",
        {
            "junior-secret": "Junior Dev",
            "senior-secret": "Senior Dev",
        },
    )

    assert api_client.authorization_headers(
        "https://api.example.test",
        "Senior Dev",
    ) == {"Authorization": "Bearer senior-secret"}


def test_multiple_tokens_for_role_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        api_client.settings,
        "api_role_tokens",
        {"first": "Senior Dev", "second": "Senior Dev"},
    )

    with pytest.raises(api_client.UIAuthenticationError, match="exactly one"):
        api_client.authorization_headers("https://api.example.test", "Senior Dev")


def test_missing_credentials_allow_only_loopback_development(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(api_client.settings, "api_role_tokens", {})

    assert api_client.authorization_headers("http://127.0.0.1:8000", "Junior Dev") == {}
    assert api_client.is_local_development_mode("http://localhost:8000")
    with pytest.raises(api_client.UIAuthenticationError, match="remote API access"):
        api_client.authorization_headers("https://api.example.test", "Junior Dev")


def test_query_sends_role_token_only_in_authorization_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = "senior-private-token"
    monkeypatch.setattr(
        api_client.settings,
        "api_role_tokens",
        {token: "Senior Dev"},
    )
    response = Mock()
    response.json.return_value = {"answer": "ok"}
    post = Mock(return_value=response)
    monkeypatch.setattr(api_client.requests, "post", post)

    result = api_client.query_api(
        "https://api.example.test",
        "Why timeout?",
        "Senior Dev",
        None,
    )

    request = post.call_args.kwargs
    assert result == {"answer": "ok"}
    assert request["headers"] == {"Authorization": f"Bearer {token}"}
    assert request["json"]["role"] == "Senior Dev"
    assert token not in post.call_args.args[0]
    assert token not in str(request["json"])


def test_source_fetch_is_server_side_and_keeps_token_out_of_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = "senior-private-token"
    monkeypatch.setattr(
        api_client.settings,
        "api_role_tokens",
        {token: "Senior Dev"},
    )
    response = Mock()
    response.text = (
        "<html><body><pre><code>"
        '<span id="L1">line one</span>\n'
        '<span id="L2">line two</span>'
        "</code></pre></body></html>"
    )
    get = Mock(return_value=response)
    monkeypatch.setattr(api_client.requests, "get", get)

    source = api_client.fetch_source(
        "https://api.example.test",
        "data/sample_codebase/api/example.py",
        "Senior Dev",
    )

    request = get.call_args.kwargs
    assert source == "line one\nline two"
    assert request["headers"] == {"Authorization": f"Bearer {token}"}
    assert request["params"] == {"role": "Senior Dev"}
    assert token not in get.call_args.args[0]
    assert token not in str(request["params"])


# ---------------------------------------------------------------------------
# Timeout / connection error distinction
# ---------------------------------------------------------------------------

def test_read_timeout_raises_ui_timeout_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """requests.ReadTimeout must surface as UITimeoutError, never as a generic
    RequestException, so the UI can display the correct message."""
    token = "senior-private-token"
    monkeypatch.setattr(
        api_client.settings,
        "api_role_tokens",
        {token: "Senior Dev"},
    )
    with patch.object(
        api_client.requests, "post",
        side_effect=requests.exceptions.ReadTimeout(),
    ):
        with pytest.raises(UITimeoutError) as exc_info:
            api_client.query_api(
                "https://api.example.test",
                "Why timeout?",
                "Senior Dev",
                None,
                read_timeout=10.0,
            )
    assert exc_info.value.timeout_s == 10.0
    assert exc_info.value.elapsed_s >= 0.0
    assert not isinstance(exc_info.value, requests.exceptions.ConnectionError)


def test_connection_error_is_not_swallowed_as_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A genuine ConnectionError must propagate as-is, not as UITimeoutError."""
    token = "senior-private-token"
    monkeypatch.setattr(
        api_client.settings,
        "api_role_tokens",
        {token: "Senior Dev"},
    )
    with patch.object(
        api_client.requests, "post",
        side_effect=requests.exceptions.ConnectionError("refused"),
    ):
        with pytest.raises(requests.exceptions.ConnectionError):
            api_client.query_api(
                "https://api.example.test",
                "Why timeout?",
                "Senior Dev",
                None,
            )


def test_query_uses_separate_connect_and_read_timeouts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify the requests.post call passes a (connect, read) tuple, not a scalar."""
    token = "senior-private-token"
    monkeypatch.setattr(
        api_client.settings,
        "api_role_tokens",
        {token: "Senior Dev"},
    )
    response = Mock()
    response.json.return_value = {"answer": "ok"}
    post = Mock(return_value=response)
    monkeypatch.setattr(api_client.requests, "post", post)

    api_client.query_api(
        "https://api.example.test",
        "Why timeout?",
        "Senior Dev",
        None,
        connect_timeout=3.0,
        read_timeout=99.0,
    )

    called_timeout = post.call_args.kwargs["timeout"]
    assert called_timeout == (3.0, 99.0), (
        f"Expected (3.0, 99.0) tuple, got {called_timeout!r}"
    )
