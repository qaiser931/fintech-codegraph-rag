"""Shared application state and FastAPI dependency providers.

All expensive objects (indexer, retriever, generator) are initialised ONCE
during lifespan startup and stored here.  Route handlers obtain them via
FastAPI's ``Depends()`` mechanism, which makes them trivially swappable
for test mocks.
"""

from __future__ import annotations

import hmac
import ipaddress
from typing import Optional

from fastapi import Header, HTTPException, Request, status
from fastapi.security import HTTPBearer
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.config import settings
from src.generation.generator import CodeRAGGenerator
from src.ingestion.indexer import CodebaseIndexer
from src.retrieval.hybrid import HybridRetriever
from src.security.rbac import rbac_manager

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer


class AppState:
    """Singleton bag-of-globals for lifespan-managed objects."""

    def __init__(self) -> None:
        self.indexer: Optional[CodebaseIndexer] = None
        self.retriever: Optional[HybridRetriever] = None
        self.generator: Optional[CodeRAGGenerator] = None
        self.ready: bool = False

    def is_ready(self) -> bool:
        return self.ready and self.generator is not None


# Module-level singleton — shared across the whole process.
bearer_scheme = HTTPBearer(auto_error=False)
app_state = AppState()


def get_authenticated_role(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> Optional[str]:
    """Resolve a configured bearer token or allow role selection on loopback."""

    authorization = (
        f"{credentials.scheme} {credentials.credentials}"
        if credentials is not None
        else None
    )

    if settings.api_role_tokens:
        resolved_role = None

        if credentials is not None and credentials.scheme.lower() == "bearer":
            for configured_token, role in settings.api_role_tokens.items():
                if hmac.compare_digest(
                    credentials.credentials,
                    configured_token,
                ):
                    resolved_role = role
                    break

        if resolved_role is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Valid bearer credentials are required.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        canonical_role = next(
            (
                allowed_role
                for allowed_role in rbac_manager.allowed_roles
                if allowed_role.lower() == resolved_role.lower()
            ),
            None,
        )

        if canonical_role is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Configured bearer token has an invalid role mapping.",
            )

        return canonical_role

    if authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer credentials are not configured.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    client_host = request.client.host if request.client is not None else ""

    try:
        is_loopback = ipaddress.ip_address(client_host).is_loopback
    except ValueError:
        is_loopback = False

    if is_loopback:
        return None

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Valid bearer credentials are required.",
        headers={"WWW-Authenticate": "Bearer"},
   )


def bind_requested_role(
    requested_role: Optional[str],
    authenticated_role: Optional[str],
) -> str:
    """Use the authenticated role and reject attempts to select another role."""
    if authenticated_role is None:
        return requested_role or "Junior Dev"
    if requested_role is None:
        return authenticated_role
    if not hmac.compare_digest(requested_role, authenticated_role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Requested role does not match authenticated role.",
        )
    return authenticated_role


# ---------------------------------------------------------------------------
# FastAPI dependency callables
# ---------------------------------------------------------------------------

def get_generator() -> CodeRAGGenerator:
    """Dependency: returns the live generator or raises 503."""
    from fastapi import HTTPException, status
    if not app_state.is_ready() or app_state.generator is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service is still initialising. Please retry in a moment.",
        )
    return app_state.generator


def get_retriever() -> HybridRetriever:
    """Return the ready retrieval pipeline without requiring generation."""
    if not app_state.ready or app_state.retriever is None:
        raise HTTPException(status_code=503, detail="Retrieval service is still initialising.")
    return app_state.retriever


def get_indexer() -> CodebaseIndexer:
    from fastapi import HTTPException, status
    if app_state.indexer is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Indexer not initialised.",
        )
    return app_state.indexer
