"""Cryptographic helper utilities for fintech webhook signature validation."""

import hashlib
import hmac
from typing import Dict


def compute_hmac_sha256(payload: str, secret_key: str) -> str:
    """Generate a hexadecimal HMAC-SHA256 signature for payload verification.

    Args:
        payload: Canonical string serialization of payload fields.
        secret_key: Shared merchant secret key.

    Returns:
        Hex-encoded HMAC-SHA256 digest string.
    """
    key_bytes = secret_key.encode("utf-8")
    payload_bytes = payload.encode("utf-8")
    signature = hmac.new(key_bytes, payload_bytes, hashlib.sha256).hexdigest()
    return signature


def verify_hmac_signature(received_signature: str, payload: str, secret_key: str) -> bool:
    """Verify webhook payload signature using constant-time comparison.

    Args:
        received_signature: Signature provided in HTTP header.
        payload: Raw payload body or canonical representation.
        secret_key: Secret key used to sign the transaction.

    Returns:
        bool: True if signature matches securely, False otherwise.
    """
    if not received_signature or not secret_key:
        return False
    expected_signature = compute_hmac_sha256(payload, secret_key)
    return hmac.compare_digest(received_signature.strip(), expected_signature.strip())


def canonicalize_dict_payload(data: Dict[str, str]) -> str:
    """Canonicalize a dictionary by sorting keys alphabetically and concatenating values.

    Args:
        data: Dictionary of callback parameters.

    Returns:
        Sorted concatenated string.
    """
    sorted_items = sorted(data.items(), key=lambda item: item[0])
    return "&".join(f"{k}={v}" for k, v in sorted_items if k != "pp_SecureHash" and k != "signature")
