"""FastAPI application entry point for the Fintech CodeGraph RAG service.

Startup (lifespan):
  1. Try to load pre-built indices from disk.
  2. If missing, run a full codebase indexing pass.
  3. Initialise HybridRetriever and CodeRAGGenerator.
  4. Mark the service as ready.

Run with:
    uvicorn src.api.main:app --reload
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.api.dependencies import app_state
from src.api.routes import router
from src.config import settings
from src.generation.generator import CodeRAGGenerator
from src.ingestion.indexer import CodebaseIndexer
from src.retrieval.hybrid import HybridRetriever
from src.telemetry import metrics_store, query_result_cache

logger = logging.getLogger(__name__)
logging.basicConfig(level=settings.log_level)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Initialise shared resources once on startup; clean up on shutdown."""
    logger.info("CodeGraph RAG service starting up…")

    indexer = CodebaseIndexer()

    # Prefer pre-built indices if they exist on disk
    graph_exists = settings.graph_store_path.exists()
    bm25_exists = settings.bm25_store_path.exists()
    vector_exists = (settings.vector_db_path / "chroma.sqlite3").exists()

    if graph_exists and bm25_exists and vector_exists:
        logger.info("Loading pre-built indices from disk…")
        try:
            indexer.load_existing_indices()
            logger.info(
                "Loaded %d chunks, %d graph nodes.",
                len(indexer.chunks),
                indexer.graph_builder.graph.number_of_nodes(),
            )
        except Exception as exc:
            logger.warning("Failed to load indices (%s); rebuilding…", exc)
            indexer.index_codebase(settings.sample_codebase_dir, base_dir=settings.base_dir)
    else:
        logger.info("Pre-built indices not found; indexing codebase…")
        stats = indexer.index_codebase(settings.sample_codebase_dir, base_dir=settings.base_dir)
        logger.info("Indexing complete: %s", stats)

    retriever = HybridRetriever(indexer)
    generator = CodeRAGGenerator(retriever)

    app_state.indexer = indexer
    app_state.retriever = retriever
    app_state.generator = generator
    app_state.ready = True

    logger.info("CodeGraph RAG service ready.")
    yield

    # Shutdown
    logger.info("CodeGraph RAG service shutting down.")
    app_state.ready = False
    metrics_store.reset()
    query_result_cache.reset()


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Fintech CodeGraph RAG",
    description=(
        "Production-grade Retrieval-Augmented Generation service for fintech codebases. "
        "Combines dense vector search, BM25 keyword search, cross-encoder reranking, "
        "and call-graph expansion with RBAC-enforced security isolation."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(router, tags=["RAG Pipeline"])


# ---------------------------------------------------------------------------
# Global exception handlers
# ---------------------------------------------------------------------------

@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={"detail": str(exc), "error_type": "validation_error"},
    )


@app.exception_handler(Exception)
async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("Unhandled exception: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal error occurred.", "error_type": "internal_error"},
    )
