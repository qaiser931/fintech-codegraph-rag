"""Isolated review fixture; not used by the application. Do not run it."""
import httpx


def fetch_demo_status():
    return httpx.get(
        "https://example.com",
        verify=False,
        timeout=5.0,
    )
