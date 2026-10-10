"""Webhook integrity and cryptographic signature verification.

SECURITY_LEVEL: CONFIDENTIAL
Ensures inbound payment notifications originate strictly from authenticated telco partners.
"""

from typing import Dict
from data.sample_codebase.secrets.signing_keys import SigningKeyStore
from data.sample_codebase.utils.crypto import canonicalize_dict_payload, verify_hmac_signature
from data.sample_codebase.utils.logging import get_logger

logger = get_logger("auth.webhook_verification")


def verify_webhook_signature(headers: Dict[str, str], payload_dict: Dict[str, str], provider: str) -> bool:
    """Validate incoming callback authenticity via HMAC signature check.

    Args:
        headers: Inbound HTTP headers.
        payload_dict: Raw incoming key-value mapping.
        provider: Provider identifier ('JAZZCASH' or 'EASYPAISA').

    Returns:
        bool: True if signature is verified, False otherwise.
    """
    if provider.upper() == "JAZZCASH":
        secret_key = SigningKeyStore.get_jazzcash_secret()
        # JazzCash sends hash in pp_SecureHash header or body field
        received_signature = headers.get("X-JazzCash-Signature") or payload_dict.get("pp_SecureHash", "")
        canonical_str = canonicalize_dict_payload(payload_dict)
        is_valid = verify_hmac_signature(received_signature, canonical_str, secret_key)
        if not is_valid:
            logger.warning("JazzCash HMAC signature verification failed.")
        return is_valid

    elif provider.upper() == "EASYPAISA":
        secret_key = SigningKeyStore.get_easypaisa_key()
        received_signature = headers.get("X-EasyPaisa-Digest", "")
        canonical_str = canonicalize_dict_payload(payload_dict)
        is_valid = verify_hmac_signature(received_signature, canonical_str, secret_key)
        if not is_valid:
            logger.warning("EasyPaisa signature verification failed.")
        return is_valid

    logger.error(f"Unsupported provider for webhook verification: {provider}")
    return False
