"""Core payment processing and settlement service.

ROOT CAUSE OF PRODUCTION INCIDENT (PLANTED ISSUE #1):
In `process_jazzcash_callback`, the service opens an atomic database transaction and acquires
an exclusive row-level lock (`SELECT ... FOR UPDATE`) on the merchant account record via
`payment_repository.acquire_account_lock()`.
Immediately afterwards, while STILL HOLDING THIS ROW LOCK inside the active transaction context,
it executes an external synchronous network HTTP call to `onelink_client.verify_switch_transaction()`.

During peak traffic periods:
- The 1LINK national switch takes 3 to 6 seconds per request due to inter-bank network congestion.
- The merchant account row lock is held for the entire duration of that external HTTP call.
- All other concurrent callbacks for this merchant queue up waiting for the same row lock.
- Once the queue wait time exceeds PostgreSQL's `lock_timeout_ms` (5000ms), queries fail with:
  "LockNotAvailable: canceling statement due to lock timeout".
- Ingress API gateways (FastAPI / Nginx) exceed their 8.0s timeout and return HTTP 504 Gateway Timeout.
"""

from decimal import Decimal
from typing import Any, Dict
from data.sample_codebase.db.models import PaymentProvider, TransactionModel, TransactionStatus
from data.sample_codebase.db.repository import payment_repository
from data.sample_codebase.db.session import get_db_session
from data.sample_codebase.integrations.onelink_client import onelink_client
from data.sample_codebase.utils.logging import get_logger

logger = get_logger("services.payment_service")


class PaymentService:
    """Orchestrates payment callback processing, row locking, and 1LINK settlement."""

    def process_jazzcash_callback(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Process verified JazzCash C2B webhook notification.

        EXECUTION TRACE PATH:
        1. Open DB transaction: get_db_session()
        2. Acquire merchant row lock: payment_repository.acquire_account_lock()
        3. [CRITICAL FLAW] Call external 1LINK switch while holding lock: onelink_client.verify_switch_transaction()
        4. Update local transaction record status: payment_repository.save_transaction()
        5. Commit transaction & release row lock.
        """
        merchant_id = payload.get("merchant_id", "MC_PK_JAZZ_99182")
        tx_ref = payload.get("transaction_ref", "")
        amount = payload.get("amount", Decimal("0.00"))
        stan = payload.get("stan", "000000")

        logger.info(f"Starting callback processing for tx_ref={tx_ref}, merchant_id={merchant_id}")

        with get_db_session() as session:
            # Step 1: Acquire exclusive row lock on the merchant account table
            # SQL: SELECT * FROM accounts WHERE merchant_id = :merchant_id FOR UPDATE;
            account = payment_repository.acquire_account_lock(session, merchant_id)
            logger.info(f"Locked account {account.account_number} for merchant {merchant_id}")

            # Step 2: ARCHITECTURAL FLAW - Holding DB row lock across synchronous external network call
            # If 1LINK switch is delayed under peak traffic, this holds the DB lock for up to 6 seconds!
            switch_res = onelink_client.verify_switch_transaction(
                tx_ref=tx_ref,
                amount=amount,
                stan=stan,
            )

            # Step 3: Record transaction in database
            status = TransactionStatus.SUCCESS if switch_res.get("switch_response_code") == "00" else TransactionStatus.FAILED
            tx_record = TransactionModel(
                id=9901,
                transaction_ref=tx_ref,
                provider=PaymentProvider.JAZZCASH,
                external_reference=stan,
                account_id=account.id,
                amount=amount,
                status=status,
            )
            payment_repository.save_transaction(session, tx_record)

            # Step 4: Adjust balance
            if status == TransactionStatus.SUCCESS:
                account.balance += amount
                logger.info(f"Credited {amount} to merchant account {account.account_number}. New balance={account.balance}")

            return {
                "transaction_ref": tx_ref,
                "status": status.value,
                "switch_status": switch_res.get("clearing_status"),
                "account_id": account.id,
            }


payment_service = PaymentService()
