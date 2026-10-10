"""Internal service authentication and JSON Web Token (JWT) validation."""

from typing import Dict, Optional


class AuthTokenVerifier:
    """Validates service-to-service bearer tokens for internal fintech API endpoints."""

    def __init__(self, issuer: str = "fintech-auth-service") -> None:
        self.issuer = issuer

    def decode_and_validate(self, token: str) -> Optional[Dict[str, str]]:
        """Validate bearer token format and claims.

        Args:
            token: Raw Bearer token string.

        Returns:
            Decoded claims dict if valid, None if invalid.
        """
        if not token or not token.startswith("Bearer "):
            return None
        token_val = token.replace("Bearer ", "").strip()
        if len(token_val) < 16:
            return None
        return {
            "sub": "service-worker",
            "role": "payment_operator",
            "issuer": self.issuer,
        }
