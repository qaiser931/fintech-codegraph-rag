"""Telemetry: in-process metrics store for latency, tokens, and cost tracking.

Stores a rolling window of query records and exposes percentile latencies,
token totals, and cost estimates.  All data is in-memory — resets on restart.
No external service required.
"""

from __future__ import annotations

import re
import hashlib
import json
import statistics
import threading
import time
from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Per-query record
# ---------------------------------------------------------------------------

@dataclass
class QueryRecord:
    """Immutable record for a single completed query."""
    query_id: str
    role: str
    latency_ms: float
    retrieval_ms: float
    generation_ms: float
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    cache_hit: bool
    timestamp: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# Cost estimation
# ---------------------------------------------------------------------------

# Approximate USD per 1 000 tokens (input/output averaged) per model family.
_COST_PER_1K: Dict[str, float] = {
    "gpt-4o":       0.005,
    "gpt-4o-mini":  0.000150,
    "gpt-4":        0.030,
    "gpt-3.5":      0.000500,
    "gemini":       0.000125,
    "groq":         0.000100,
}


def estimate_cost(model: str, total_tokens: int) -> float:
    """Return approximate USD cost for *total_tokens* with *model*."""
    rate = 0.002  # fallback $/1k tokens
    model_lower = model.lower()
    for key, r in _COST_PER_1K.items():
        if key in model_lower:
            rate = r
            break
    return round(total_tokens * rate / 1000, 8)


# ---------------------------------------------------------------------------
# Trace redaction / structured trace records
# ---------------------------------------------------------------------------

_SENSITIVE_FIELD_RE = re.compile(
    r"(?i)(?:api[_-]?key|client[_-]?secret|secret|access[_-]?token|"
    r"refresh[_-]?token|authorization|password|passwd|signature|"
    r"private[_-]?key|signing[_-]?key)"
)
_SENSITIVE_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(api[_-]?key|client[_-]?secret|secret|access[_-]?token|"
    r"refresh[_-]?token|authorization|password|passwd|signature|"
    r"private[_-]?key|signing[_-]?key)(\s*[:=]\s*)"
    r"(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)"
)
_PRIVATE_KEY_RE = re.compile(
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z0-9 ]*PRIVATE KEY-----"
)
_BEARER_TOKEN_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
_OPAQUE_SECRET_RE = re.compile(
    r"(?i)\b(?:sk-(?:proj-)?[A-Za-z0-9_-]{20,}|AKIA[A-Z0-9]{16})\b"
)
_JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")


def _redact_sensitive_value(value: Any) -> Any:
    """Return a JSON-safe value with obvious secret material redacted."""
    if value is None:
        return None

    if isinstance(value, dict):
        return {
            str(key): (
                "[REDACTED]"
                if _SENSITIVE_FIELD_RE.fullmatch(str(key))
                else _redact_sensitive_value(item)
            )
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [_redact_sensitive_value(item) for item in value]

    if isinstance(value, tuple):
        return [_redact_sensitive_value(item) for item in value]

    if isinstance(value, str):
        if not value.strip():
            return value

        redacted = _SENSITIVE_ASSIGNMENT_RE.sub(
            r"\1\2[REDACTED]",
            value,
        )
        redacted = _PRIVATE_KEY_RE.sub("[REDACTED PRIVATE KEY]", redacted)
        redacted = _BEARER_TOKEN_RE.sub("Bearer [REDACTED]", redacted)
        redacted = _OPAQUE_SECRET_RE.sub("[REDACTED TOKEN]", redacted)
        return _JWT_RE.sub("[REDACTED JWT]", redacted)

    return value


def contains_sensitive_material(value: Any) -> bool:
    """Return whether a value contains credential-like material."""
    if isinstance(value, dict):
        return any(
            _SENSITIVE_FIELD_RE.fullmatch(str(key))
            or contains_sensitive_material(item)
            for key, item in value.items()
        )

    if isinstance(value, (list, tuple)):
        return any(contains_sensitive_material(item) for item in value)

    if isinstance(value, str):
        return bool(
            _SENSITIVE_ASSIGNMENT_RE.search(value)
            or _PRIVATE_KEY_RE.search(value)
            or _BEARER_TOKEN_RE.search(value)
            or _OPAQUE_SECRET_RE.search(value)
            or _JWT_RE.search(value)
        )

    return False


def build_query_cache_key(
    query: str,
    role: str,
    stack_trace: Optional[str] = None,
) -> Optional[str]:
    """Build an opaque cache key; sensitive requests are never cached."""
    if contains_sensitive_material([query, role, stack_trace]):
        return None

    payload = {
        "query": " ".join(query.split()),
        "role": role,
        "stack_trace": " ".join(stack_trace.split()) if stack_trace else None,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class QueryResultCache:
    """Bounded thread-safe LRU cache for safe completed query results."""

    def __init__(self, max_entries: int = 256) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be at least 1")
        self._lock = threading.Lock()
        self._records: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self._max_entries = max_entries

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            value = self._records.get(key)
            if value is None:
                return None
            self._records.move_to_end(key)
            return deepcopy(value)

    def set(self, key: str, value: Dict[str, Any]) -> bool:
        if contains_sensitive_material(value):
            return False

        with self._lock:
            self._records[key] = deepcopy(value)
            self._records.move_to_end(key)
            while len(self._records) > self._max_entries:
                self._records.popitem(last=False)
        return True

    def __len__(self) -> int:
        with self._lock:
            return len(self._records)

    def reset(self) -> None:
        with self._lock:
            self._records.clear()


@dataclass
class QueryTrace:
    """Minimal structured trace for one query request."""

    trace_id: str
    timestamp: float
    raw_query: str
    role: str
    retrieved_chunks: List[Dict[str, Any]] = field(default_factory=list)
    reranker_scores: List[Dict[str, Any]] = field(default_factory=list)
    graph_expansion_steps: List[str] = field(default_factory=list)
    final_context: List[Any] = field(default_factory=list)
    citations: List[Dict[str, Any]] = field(default_factory=list)
    cache_hit: bool = False
    answer_status: str = ""
    latency_ms: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "trace_id": self.trace_id,
            "timestamp": self.timestamp,
            "raw_query": self.raw_query,
            "role": self.role,
            "retrieved_chunks": self.retrieved_chunks,
            "reranker_scores": self.reranker_scores,
            "graph_expansion_steps": self.graph_expansion_steps,
            "final_context": self.final_context,
            "citations": self.citations,
            "cache_hit": self.cache_hit,
            "answer_status": self.answer_status,
            "latency_ms": self.latency_ms,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "cost_usd": self.cost_usd,
        }
        return _redact_sensitive_value(payload)


class TraceStore:
    """Lightweight in-memory structured trace store."""

    def __init__(self, max_traces: int = 1_000) -> None:
        self._lock = threading.Lock()
        self._records: List[Dict[str, Any]] = []
        self._max = max_traces

    def record(self, trace: QueryTrace | Dict[str, Any]) -> None:
        with self._lock:
            payload = trace.to_dict() if isinstance(trace, QueryTrace) else _redact_sensitive_value(trace)
            self._records.append(payload)
            if len(self._records) > self._max:
                self._records.pop(0)

    def latest(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            if not self._records:
                return None
            return dict(self._records[-1])

    def list(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [dict(item) for item in self._records]

    def reset(self) -> None:
        with self._lock:
            self._records.clear()


# ---------------------------------------------------------------------------
# Metrics store (thread-safe singleton)
# ---------------------------------------------------------------------------

class MetricsStore:
    """Thread-safe rolling metrics store."""

    def __init__(self, max_records: int = 10_000) -> None:
        self._lock = threading.Lock()
        self._records: List[QueryRecord] = []
        self._max = max_records
        self._cache_hits = 0
        self._total_queries = 0

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def record(self, rec: QueryRecord) -> None:
        with self._lock:
            self._total_queries += 1
            if rec.cache_hit:
                self._cache_hits += 1
            self._records.append(rec)
            if len(self._records) > self._max:
                self._records.pop(0)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def summary(self) -> Dict:
        with self._lock:
            records = list(self._records)

        if not records:
            return {
                "total_queries": 0,
                "p50_latency_ms": 0.0,
                "p95_latency_ms": 0.0,
                "avg_latency_ms": 0.0,
                "total_prompt_tokens": 0,
                "total_completion_tokens": 0,
                "total_tokens": 0,
                "avg_tokens_per_query": 0.0,
                "estimated_cost_usd": 0.0,
                "cache_hit_rate": 0.0,
            }

        latencies = sorted(r.latency_ms for r in records)
        n = len(latencies)

        def percentile(data: List[float], p: float) -> float:
            """Calculate a percentile by linear interpolation at (n - 1) * p."""
            if not data:
                return 0.0
            rank = (len(data) - 1) * p / 100
            lower_index = int(rank)
            upper_index = min(lower_index + 1, len(data) - 1)
            fraction = rank - lower_index
            value = data[lower_index] + (
                data[upper_index] - data[lower_index]
            ) * fraction
            return round(value, 2)

        total_pt = sum(r.prompt_tokens for r in records)
        total_ct = sum(r.completion_tokens for r in records)
        total_tok = sum(r.total_tokens for r in records)
        total_cost = sum(r.cost_usd for r in records)

        with self._lock:
            tq = self._total_queries
            ch = self._cache_hits

        return {
            "total_queries": tq,
            "p50_latency_ms": percentile(latencies, 50),
            "p95_latency_ms": percentile(latencies, 95),
            "avg_latency_ms": round(sum(latencies) / n, 2),
            "total_prompt_tokens": total_pt,
            "total_completion_tokens": total_ct,
            "total_tokens": total_tok,
            "avg_tokens_per_query": round(total_tok / n, 1),
            "estimated_cost_usd": round(total_cost, 6),
            "cache_hit_rate": round(ch / tq, 4) if tq else 0.0,
        }

    def reset(self) -> None:
        with self._lock:
            self._records.clear()
            self._cache_hits = 0
            self._total_queries = 0


# Singleton
metrics_store = MetricsStore()
trace_store = TraceStore()
query_result_cache = QueryResultCache()


def create_query_trace(
    *,
    trace_id: str,
    raw_query: str,
    role: str,
    retrieved_chunks: Optional[List[Dict[str, Any]]] = None,
    reranker_scores: Optional[List[Dict[str, Any]]] = None,
    graph_expansion_steps: Optional[List[str]] = None,
    final_context: Optional[List[Any]] = None,
    citations: Optional[List[Dict[str, Any]]] = None,
    cache_hit: bool = False,
    answer_status: str = "",
    latency_ms: float = 0.0,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int = 0,
    cost_usd: float = 0.0,
) -> QueryTrace:
    """Create a JSON-compatible structured trace record for a /query call."""
    trace = QueryTrace(
        trace_id=trace_id,
        timestamp=time.time(),
        raw_query=_redact_sensitive_value(raw_query),
        role=role,
        retrieved_chunks=list(retrieved_chunks or []),
        reranker_scores=list(reranker_scores or []),
        graph_expansion_steps=list(graph_expansion_steps or []),
        final_context=list(final_context or []),
        citations=list(citations or []),
        cache_hit=cache_hit,
        answer_status=str(answer_status),
        latency_ms=float(latency_ms),
        prompt_tokens=int(prompt_tokens),
        completion_tokens=int(completion_tokens),
        total_tokens=int(total_tokens),
        cost_usd=float(cost_usd),
    )
    return trace
