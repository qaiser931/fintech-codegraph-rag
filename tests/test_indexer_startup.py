"""Imports must not initialise a neural model before explicit startup."""

import subprocess
import sys
from pathlib import Path

from src.config import settings


def test_authentication_starts_with_empty_test_mapping():
    assert settings.api_role_tokens == {}


def test_api_and_indexing_cli_import_without_loading_embedding_model():
    # A fresh interpreter catches import side effects even when other test
    # modules have already imported the API. Fail before any model download.
    result = subprocess.run(
        [sys.executable, "-c", """
import src.retrieval.dense as dense
def forbidden_model_load():
    raise AssertionError('Embedding model loaded at import time')
dense.get_embedding_engine = forbidden_model_load
import src.ingestion.indexer
import src.api.main
import scripts.run_indexing
"""],
        cwd=settings.base_dir,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_default_persistence_paths_are_outside_the_project():
    project = settings.base_dir.resolve()
    for path in (
        settings.vector_db_path,
        settings.graph_store_path,
        settings.bm25_store_path,
        settings.telemetry_log_dir,
    ):
        assert not Path(path).resolve().is_relative_to(project), path
