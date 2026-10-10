"""Pytest configuration and environment fixtures."""

import os
import sys
import tempfile
from pathlib import Path

import pytest

# Ensure repository root is on sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Configure disposable stores BEFORE collection imports src.config. A fixture
# runs too late: Settings.ensure_directories() also runs during module import.
# Keep the real sample-codebase/base paths so symbol IDs remain unchanged.
_test_stores = tempfile.TemporaryDirectory(prefix="codegraph-pytest-", ignore_cleanup_errors=True)
_store_root = Path(_test_stores.name)
_test_environment = {
    "VECTOR_DB_PATH": str(_store_root / "vectors"),
    "GRAPH_STORE_PATH": str(_store_root / "graph" / "codebase_graph.json"),
    "BM25_STORE_PATH": str(_store_root / "bm25" / "bm25_index.pkl"),
    "TELEMETRY_LOG_DIR": str(_store_root / "telemetry"),
    # Authentication tests configure their own synthetic tokens. Host .env
    # credentials must not determine the baseline for offline tests.
    "API_ROLE_TOKENS": "{}",
}
_previous_environment = {name: os.environ.get(name) for name in _test_environment}
os.environ.update(_test_environment)


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config):
    # Avoid a stale/shared pytest-of-<user> directory with incompatible Windows
    # permissions. Pytest owns only this fresh child of our disposable folder.
    if config.option.basetemp is None:
        config.option.basetemp = str(_store_root / "pytest-tmp")


@pytest.fixture(autouse=True)
def isolated_authentication_baseline(monkeypatch):
    from src.config import settings

    # Pydantic Settings merges dictionaries across environment/dotenv sources:
    # API_ROLE_TOKENS='{}' alone does not erase a nonempty host .env mapping.
    # Override the object only within each test. Authentication tests can still
    # install synthetic mappings with the same monkeypatch fixture.
    monkeypatch.setattr(settings, "api_role_tokens", {})


def pytest_unconfigure(config):
    for name, value in _previous_environment.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value
    # Chroma may retain SQLite handles until process exit on Windows. Cleanup
    # is best effort; this directory is never a deployed index directory.
    _test_stores.cleanup()
