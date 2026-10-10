"""Pydantic request/response models for the CodeGraph RAG API."""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class AnswerStatus(str, Enum):
    """Confidence classification for the generated answer."""
    SUPPORTED = "SUPPORTED"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
    CONFLICTING_EVIDENCE = "CONFLICTING_EVIDENCE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class AllowedRole(str, Enum):
    JUNIOR_DEV = "Junior Dev"
    SENIOR_DEV = "Senior Dev"
    SECURITY_LEAD = "Security Lead"


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------

class QueryRequest(BaseModel):
    """POST /query request body."""

    query: str = Field(
        ...,
        min_length=3,
        max_length=2000,
        description="Natural-language question about the codebase.",
        examples=["Why does the JazzCash callback handler throw a timeout during peak traffic?"],
    )
    role: str = Field(
        default="Junior Dev",
        description="RBAC role controlling data access and answer persona.",
        examples=["Junior Dev", "Senior Dev", "Security Lead"],
    )
    stack_trace: Optional[str] = Field(
        default=None,
        max_length=8000,
        description="Optional stack trace to append to the query for richer context.",
    )

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        allowed = {"Junior Dev", "Senior Dev", "Security Lead"}
        if v not in allowed:
            raise ValueError(f"role must be one of {sorted(allowed)}, got '{v}'")
        return v


# ---------------------------------------------------------------------------
# Response
# ---------------------------------------------------------------------------

class CitationItem(BaseModel):
    """A single cited code symbol."""
    doc_id: str
    symbol_name: str
    file_path: str
    start_line: int
    end_line: int
    security_level: str
    source: str = "retrieval"


class RetrievedItem(BaseModel):
    """A single item from the hybrid retrieval pipeline."""
    doc_id: str
    symbol_name: str
    file_path: str
    start_line: int
    end_line: int
    source: str          # "hybrid" or "graph"
    rrf_score: float
    rerank_score: Optional[float] = None
    hop: int = 0
    direction: Optional[str] = None


class RetrievalResponse(BaseModel):
    """Code evidence only; no generated answer or confidence classification."""

    query: str
    role: str
    sources: List[CitationItem] = Field(default_factory=list)
    retrieved_items: List[RetrievedItem] = Field(default_factory=list)
    call_path: List[str] = Field(default_factory=list)
    latency_ms: float


class QueryResponse(BaseModel):
    """POST /query response body."""

    trace_id: str = Field(
        default="",
        description="Unique request trace identifier for structured telemetry.",
    )
    query: str
    role: str
    answer: str
    status: AnswerStatus
    citations: List[CitationItem] = Field(default_factory=list)
    retrieved_items: List[RetrievedItem] = Field(default_factory=list)
    call_path: List[str] = Field(
        default_factory=list,
        description="Human-readable execution path(s): 'A → B → C'.",
    )
    model: str
    provider: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    latency_ms: float
    cost_usd: float


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    status: str = "healthy"
    indexed: bool = False
    chunks: int = 0
    graph_nodes: int = 0
    graph_edges: int = 0


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

class MetricsResponse(BaseModel):
    total_queries: int
    p50_latency_ms: float
    p95_latency_ms: float
    avg_latency_ms: float
    total_prompt_tokens: int
    total_completion_tokens: int
    total_tokens: int
    avg_tokens_per_query: float
    estimated_cost_usd: float
    cache_hit_rate: float


# ---------------------------------------------------------------------------
# Error
# ---------------------------------------------------------------------------

class ErrorResponse(BaseModel):
    detail: str
    error_type: str = "api_error"
