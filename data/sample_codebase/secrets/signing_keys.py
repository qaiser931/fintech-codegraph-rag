"""Restricted cryptographic key store and hardware security module (HSM) tokens.

SECURITY_LEVEL: RESTRICTED
CLEARANCE_REQUIRED: Security Lead
This file contains sensitive HMAC secret keys and private RSA keys for 1LINK and JazzCash.
Unauthorized access will violate SBP (State Bank of Pakistan) payment security guidelines.
"""

from typing import Dict


class SigningKeyStore:
    """In-memory encrypted key storage for fintech cryptographic handshakes."""

    # HMAC-SHA256 Shared Secret for JazzCash Webhook Integrity
    JAZZCASH_HMAC_SECRET: str = "sec_live_jazzcash_e98234ab881726cdef128940"

    # EasyPaisa Merchant Hash Salt
    EASYPAISA_HASH_KEY: str = "sec_live_easypaisa_771920aa99182374bb554"

    # 1LINK Switch PKI Private Key identifier (HSM slot 4)
    ONELINK_HSM_KEY_ID: str = "HSM-PKI-SLOT-04-1LINK-MUTUAL-TLS"

    @classmethod
    def get_jazzcash_secret(cls) -> str:
        """Retrieve JazzCash merchant HMAC secret key.

        Returns:
            str: 256-bit secret token.
        """
        return cls.JAZZCASH_HMAC_SECRET

    @classmethod
    def get_easypaisa_key(cls) -> str:
        """Retrieve EasyPaisa merchant hash secret key.

        Returns:
            str: Merchant hash salt.
        """
        return cls.EASYPAISA_HASH_KEY

    @classmethod
    def get_onelink_credentials(cls) -> Dict[str, str]:
        """Fetch 1LINK mutual TLS authentication credentials.

        Returns:
            Dict[str, str]: Key ID and client certificate fingerprint.
        """
        return {
            "key_id": cls.ONELINK_HSM_KEY_ID,
            "cert_fingerprint": "SHA256:7B:3A:99:F1:C2:55:09:A1:88:E3:44:90:12:33:41:AA",
        }
