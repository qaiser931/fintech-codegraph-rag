"""Narrowly scoped test API launcher with automatic re-indexing guard."""

import sys
from pathlib import Path

# Ensure /app is in sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

import uvicorn
from src.ingestion.indexer import CodebaseIndexer


def _block_reindexing(*args, **kwargs):
    raise RuntimeError("Automatic re-indexing is blocked in this container.")


CodebaseIndexer.index_codebase = _block_reindexing

if __name__ == "__main__":
    from src.api.main import app

    uvicorn.run(app, host="0.0.0.0", port=8000)
