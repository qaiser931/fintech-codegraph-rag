"""API subpackage: FastAPI endpoints, request/response models."""

from src.api.models import QueryRequest, QueryResponse, HealthResponse, MetricsResponse


def __getattr__(name):
    # Importing API contracts/dependencies must not initialize the local
    # Chroma/PyTorch runtime. Preserve the former app export on explicit access.
    if name == "app":
        from src.api.main import app
        return app
    raise AttributeError(name)

__all__ = ["app", "QueryRequest", "QueryResponse", "HealthResponse", "MetricsResponse"]
