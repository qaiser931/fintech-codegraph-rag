"""Role-Based Access Control (RBAC) and Pre-Retrieval Authorization Filters.

Enforces strict security isolation ensuring confidential and restricted code chunks
(e.g., cryptographic keys, HSM tokens, webhook secrets) are never loaded into memory
or returned for unauthorized user roles.
"""

from typing import Any, Dict, List, Optional, Set
from src.config import settings
from src.ingestion.chunker import CodeChunk


class RBACManager:
    """Manages role-based authorization clearances and retrieval filter specifications."""

    def __init__(self) -> None:
        self.role_clearance: Dict[str, Set[str]] = settings.role_clearance
        self.allowed_roles: List[str] = settings.allowed_roles

    def get_clearance_for_role(self, role: str) -> Set[str]:
        """Return the set of security clearance levels granted to a given role.

        Args:
            role: User role ("Junior Dev", "Senior Dev", "Security Lead").

        Returns:
            Set of allowed security levels, e.g. {"public", "internal"}.

        Raises:
            ValueError: If the role is unknown or unauthorized.
        """
        # Case-insensitive role matching with default fallback
        matched_role = next((r for r in self.allowed_roles if r.lower() == role.lower()), None)
        if not matched_role:
            raise ValueError(f"Unknown role '{role}'. Allowed roles: {self.allowed_roles}")
        return self.role_clearance[matched_role]

    def is_chunk_authorized(self, chunk: CodeChunk | Dict[str, Any], role: str) -> bool:
        """Check whether a code chunk is accessible to a given role."""
        clearance = self.get_clearance_for_role(role)
        if isinstance(chunk, CodeChunk):
            return chunk.security_level.lower() in clearance
        elif isinstance(chunk, dict):
            sec_level = chunk.get("security_level") or chunk.get("metadata", {}).get("security_level", "internal")
            return str(sec_level).lower() in clearance
        return False

    def filter_chunks(self, chunks: List[Any], role: str) -> List[Any]:
        """Filter a list of CodeChunks or chunk dictionaries according to role clearance."""
        clearance = self.get_clearance_for_role(role)
        authorized = []
        for ch in chunks:
            if isinstance(ch, CodeChunk):
                if ch.security_level.lower() in clearance:
                    authorized.append(ch)
            elif isinstance(ch, dict):
                sec_level = ch.get("security_level") or ch.get("metadata", {}).get("security_level", "internal")
                if str(sec_level).lower() in clearance:
                    authorized.append(ch)
        return authorized

    def build_vector_filter(self, role: str, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """Construct a structured metadata filter for Vector DB queries.

        Args:
            role: User role.
            tenant_id: Optional tenant isolation key.

        Returns:
            Dictionary filter suitable for vector databases.
        """
        clearance = list(self.get_clearance_for_role(role))
        flt: Dict[str, Any] = {
            "security_level": {"$in": clearance}
        }
        if tenant_id:
            flt["tenant_id"] = tenant_id
        return flt

    def validate_file_access(self, file_path: str, role: str) -> bool:
        """Check if a file path is accessible to the specified role based on path rules."""
        norm_path = file_path.replace("\\", "/").lower()
        clearance = self.get_clearance_for_role(role)

        for pattern, level in settings.security_path_rules.items():
            if pattern.lower() in norm_path:
                return level in clearance

        return "internal" in clearance


# Singleton RBAC manager
rbac_manager = RBACManager()
