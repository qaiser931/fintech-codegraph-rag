"""Authenticated server-side client for the CodeGraph API."""

from __future__ import annotations

import ipaddress
import math
import os
from html.parser import HTMLParser
from urllib.parse import quote, urlsplit

import requests

from src.config import settings

# Finite network waits; read timeout is not a total query deadline.
def _validate_timeout(value: float, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a positive finite number.") from None
    if not math.isfinite(result) or result <= 0:
        raise ValueError(f"{name} must be a positive finite number.")
    return result


def _timeout_from_env(name: str, default: float) -> float:
    return _validate_timeout(os.getenv(name, str(default)), name)


CONNECT_TIMEOUT = _timeout_from_env("CODEGRAPH_CONNECT_TIMEOUT", 5.0)
# Provisional setting; live uncached performance still requires verification.
QUERY_READ_TIMEOUT = _timeout_from_env("CODEGRAPH_QUERY_READ_TIMEOUT", 240.0)


RETRIEVAL_READ_TIMEOUT = _timeout_from_env("CODEGRAPH_RETRIEVAL_READ_TIMEOUT", 60.0)


class UITimeoutError(requests.exceptions.ReadTimeout):
    """A response wait expired; backend completion remains unknown."""

    def __init__(self, elapsed_s: float, timeout_s: float) -> None:
        self.elapsed_s = elapsed_s
        self.timeout_s = timeout_s
        super().__init__(
            f"No API response was received after {elapsed_s:.0f} seconds "
            f"(configured read timeout: {timeout_s:.0f} seconds). "
            "Backend processing may continue; completion is unknown."
        )


class UIAuthenticationError(ValueError):
    """Raised when UI/API role credentials are not safely configured."""


def describe_query_error(exc: Exception) -> tuple[str, str]:
    """Return the severity and message used by the Streamlit query handler."""
    if isinstance(exc, UITimeoutError):
        return "warning", (
            f"No API response was received after {exc.elapsed_s:.0f} seconds "
            f"(configured read timeout: {exc.timeout_s:.0f} seconds). "
            "The backend may still be processing; completion is unknown. "
            "Check API health and logs before submitting another request. "
            "No automatic retry was made."
        )
    if isinstance(exc, requests.exceptions.ConnectTimeout):
        return "error", (
            "Connecting to the API timed out. Check the API address and service."
        )
    if isinstance(exc, requests.ConnectionError):
        return "error", (
            "Could not reach the API. Check the API address and service."
        )
    if isinstance(exc, requests.HTTPError):
        code = exc.response.status_code if exc.response is not None else None
        if code == 401:
            return "error", (
                "Authentication failed (HTTP 401). Check server-side role credentials."
            )
        if code == 403:
            return "error", (
                "Access denied (HTTP 403). Check the selected role and its credentials."
            )
        if code == 429:
            return "warning", (
                "Cloud generation rate limit reached (HTTP 429). Wait before "
                "trying again, or use Explore code to inspect the evidence. "
                "No automatic retry was made."
            )
        if code == 504:
            return "warning", (
                "Answer generation timed out (HTTP 504). Check the provider "
                "connection, or use Explore code to inspect the evidence. "
                "No automatic retry was made."
            )
        if code == 503:
            try:
                detail = exc.response.json().get("detail")
            except (ValueError, AttributeError):
                detail = None
            if detail == "Cloud generation credentials were rejected.":
                return "error", (
                    "The cloud provider rejected its API credentials (HTTP 503). "
                    "Check the server-side Groq key and model permissions."
                )
        if code is not None and code >= 500:
            return "error", (
                f"The backend failed (HTTP {code}). Check the API logs."
            )
        return "error", f"The API rejected the request (HTTP {code or 'unknown'})."
    if isinstance(exc, UIAuthenticationError):
        return "error", (
            "Authentication configuration is invalid. Check server-side role credentials."
        )
    return "error", "An unexpected network error occurred. Check the API logs."


def is_loopback_api_url(api_url: str) -> bool:
    hostname = urlsplit(api_url).hostname
    if not hostname:
        return False
    if hostname.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def is_local_development_mode(api_url: str) -> bool:
    return not settings.api_role_tokens and is_loopback_api_url(api_url)


def authorization_headers(api_url: str, role: str) -> dict[str, str]:
    """Resolve exactly one server-side token for the selected role."""
    token_map = settings.api_role_tokens
    if not token_map:
        if is_loopback_api_url(api_url):
            return {}
        raise UIAuthenticationError(
            "No API_ROLE_TOKENS credentials are configured for remote API access."
        )

    role_tokens = [
        token
        for token, mapped_role in token_map.items()
        if mapped_role.casefold() == role.casefold()
    ]
    if len(role_tokens) != 1:
        raise UIAuthenticationError(
            f"Configure exactly one API_ROLE_TOKENS entry for the {role} role."
        )

    return {"Authorization": f"Bearer {role_tokens[0]}"}


class _CodeHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._in_code = False
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "code":
            self._in_code = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "code":
            self._in_code = False

    def handle_data(self, data: str) -> None:
        if self._in_code:
            self.parts.append(data)


def query_api(
    api_url: str,
    query: str,
    role: str,
    stack_trace: str | None,
    *,
    connect_timeout: float = CONNECT_TIMEOUT,
    read_timeout: float = QUERY_READ_TIMEOUT,
) -> dict:
    """Send a role-bound authenticated request from the Streamlit server.

    Raises
    ------
    UITimeoutError
        When the API accepts the connection but does not return a response
        within *read_timeout* seconds.  The backend may still be processing.
    UIAuthenticationError
        When role-token configuration is missing or ambiguous.
    requests.HTTPError
        For 4xx/5xx responses from the API.
    requests.ConnectionError
        When the API host is unreachable.
    """
    connect_timeout = _validate_timeout(connect_timeout, "connect_timeout")
    read_timeout = _validate_timeout(read_timeout, "read_timeout")
    import time

    payload = {
        "query": query,
        "role": role,
        "stack_trace": stack_trace or None,
    }
    t_start = time.monotonic()
    try:
        response = requests.post(
            f"{api_url.rstrip('/')}/query",
            json=payload,
            headers=authorization_headers(api_url, role),
            timeout=(connect_timeout, read_timeout),
        )
    except requests.exceptions.ReadTimeout as exc:
        elapsed = time.monotonic() - t_start
        raise UITimeoutError(elapsed, read_timeout) from exc
    response.raise_for_status()
    return response.json()


def retrieve_api(
    api_url: str,
    query: str,
    role: str,
    stack_trace: str | None,
    *,
    connect_timeout: float = CONNECT_TIMEOUT,
    read_timeout: float = RETRIEVAL_READ_TIMEOUT,
) -> dict:
    """Retrieve code evidence once, using server-side role credentials."""
    import time

    connect_timeout = _validate_timeout(connect_timeout, "connect_timeout")
    read_timeout = _validate_timeout(read_timeout, "read_timeout")
    started = time.monotonic()
    try:
        response = requests.post(
            f"{api_url.rstrip('/')}/retrieve",
            json={"query": query, "role": role, "stack_trace": stack_trace or None},
            headers=authorization_headers(api_url, role),
            timeout=(connect_timeout, read_timeout),
        )
    except requests.exceptions.ReadTimeout as exc:
        raise UITimeoutError(time.monotonic() - started, read_timeout) from exc
    response.raise_for_status()
    return response.json()


def fetch_source(api_url: str, file_path: str, role: str) -> str:
    """Fetch authorized source server-side; never include credentials in its URL."""
    safe_path = quote(file_path.replace("\\", "/"), safe="/")
    response = requests.get(
        f"{api_url.rstrip('/')}/source/{safe_path}",
        params={"role": role},
        headers=authorization_headers(api_url, role),
        timeout=30,
    )
    response.raise_for_status()

    parser = _CodeHTMLParser()
    parser.feed(response.text)
    if not parser.parts:
        raise ValueError("The source endpoint returned no code content.")
    return "".join(parser.parts)