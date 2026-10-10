"""Unit tests verifying Phase 1 setup, project structure, settings, and mock fintech codebase."""

import inspect
from decimal import Decimal
from pathlib import Path
import pytest
from src.config import settings
from data.sample_codebase.auth.webhook_verification import verify_webhook_signature
from data.sample_codebase.config.settings import app_settings
from data.sample_codebase.db.models import TransactionStatus
from data.sample_codebase.db.repository import payment_repository
from data.sample_codebase.db.session import DatabaseSession, get_db_session
from data.sample_codebase.integrations.easypaisa_gateway import easypaisa_client
from data.sample_codebase.integrations.jazzcash_gateway import jazzcash_client
from data.sample_codebase.integrations.onelink_client import onelink_client
from data.sample_codebase.secrets.signing_keys import SigningKeyStore
from data.sample_codebase.services.payment_service import payment_service
from data.sample_codebase.utils.crypto import compute_hmac_sha256, verify_hmac_signature
from data.sample_codebase.utils.retry import retry_on_exception


def test_project_structure_and_settings() -> None:
    """Validate core directories and security settings exist."""
    assert settings.base_dir.exists()
    assert settings.sample_codebase_dir.exists()
    assert settings.vector_db_path.exists()
    assert "Junior Dev" in settings.role_clearance
    assert "Senior Dev" in settings.role_clearance
    assert "Security Lead" in settings.role_clearance

    # Restricted security level should only be cleared for Security Lead
    assert "restricted" in settings.role_clearance["Security Lead"]
    assert "restricted" not in settings.role_clearance["Junior Dev"]
    assert "restricted" not in settings.role_clearance["Senior Dev"]


def test_sample_codebase_file_count() -> None:
    """Verify that the mock fintech codebase contains between 15 and 35 Python source files."""
    py_files = list(settings.sample_codebase_dir.rglob("*.py"))
    assert len(py_files) >= 15, f"Expected at least 15 files, found {len(py_files)}"


def test_hmac_crypto_and_webhook_verification() -> None:
    """Test cryptographic signature generation and verification."""
    secret = SigningKeyStore.get_jazzcash_secret()
    payload = "pp_Amount=10000&pp_MerchantID=MC_PK_JAZZ_99182&pp_TxnRefNo=T202609301201"
    sig = compute_hmac_sha256(payload, secret)

    assert verify_hmac_signature(sig, payload, secret) is True
    assert verify_hmac_signature("invalid_signature", payload, secret) is False

    # Test full webhook verification helper
    payload_dict = {
        "pp_Amount": "10000",
        "pp_MerchantID": "MC_PK_JAZZ_99182",
        "pp_TxnRefNo": "T202609301201",
        "pp_SecureHash": sig,
    }
    headers = {"X-JazzCash-Signature": sig}
    assert verify_webhook_signature(headers, payload_dict, "JAZZCASH") is True


def test_planted_bug_1_db_lock_held_during_onelink_call() -> None:
    """Validate Planted Issue 1: PaymentService acquires a DB row lock and calls 1LINK within the session."""
    code = inspect.getsource(payment_service.process_jazzcash_callback)

    # Check that acquire_account_lock occurs before onelink_client.verify_switch_transaction
    lock_pos = code.find("acquire_account_lock")
    switch_call_pos = code.find("verify_switch_transaction")

    assert lock_pos != -1, "acquire_account_lock must be called in process_jazzcash_callback"
    assert switch_call_pos != -1, "verify_switch_transaction must be called in process_jazzcash_callback"
    assert lock_pos < switch_call_pos, "Row lock must be acquired BEFORE the external 1LINK switch call"

    # Execute flow to verify execution
    payload = {
        "merchant_id": "MC_PK_JAZZ_99182",
        "transaction_ref": "TXN_TEST_001",
        "amount": Decimal("5000.00"),
        "stan": "123456",
    }
    result = payment_service.process_jazzcash_callback(payload)
    assert result["status"] == TransactionStatus.SUCCESS.value
    assert result["switch_status"] == "CLEARED"


def test_planted_bug_2_easypaisa_missing_timeout() -> None:
    """Validate Planted Issue 2: EasyPaisa inquire_transaction_status lacks a timeout parameter."""
    code = inspect.getsource(easypaisa_client.inquire_transaction_status)
    assert "timeout" in code.lower()
    # Confirm docstring/implementation notes the defect
    assert "WITHOUT timeout limit" in code or "timeout=None" in code or "NO timeout" in code


def test_planted_bug_3_retry_storm_decorator() -> None:
    """Validate Planted Issue 3: Retry decorator executes retries with fixed delay without jitter."""
    attempts = 0

    @retry_on_exception(max_retries=3, delay_seconds=0.01)
    def flaky_func() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise ConnectionError("1LINK switch connection timeout")
        return "SUCCESS"

    res = flaky_func()
    assert res == "SUCCESS"
    assert attempts == 3
