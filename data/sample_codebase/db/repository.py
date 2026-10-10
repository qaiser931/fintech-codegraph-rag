"""Data access repository handling atomic row locking and ledger persistence."""

from decimal import Decimal
from typing import Optional
from data.sample_codebase.db.models import AccountModel, TransactionModel, TransactionStatus, WebhookAuditLog
from data.sample_codebase.db.session import DatabaseSession
from data.sample_codebase.utils.logging import get_logger

logger = get_logger("db.repository")


class PaymentRepository:
    """Repository managing transactions, account balances, and row locks."""

    def __init__(self) -> None:
        # In-memory mock state representing PostgreSQL tables
        self._accounts: dict[str, AccountModel] = {
            "MC_PK_JAZZ_99182": AccountModel(
                id=1,
                account_number="PK99JAZZ00001001",
                merchant_id="MC_PK_JAZZ_99182",
                balance=Decimal("2500000.00"),
            ),
            "EP_STORE_8821": AccountModel(
                id=2,
                account_number="PK99EP00002002",
                merchant_id="EP_STORE_8821",
                balance=Decimal("1800000.00"),
            ),
        }
        self._transactions: dict[str, TransactionModel] = {}
        self._audit_logs: list[WebhookAuditLog] = []

    def acquire_account_lock(self, session: DatabaseSession, merchant_id: str) -> AccountModel:
        """Acquire an exclusive row lock on the merchant account.

        SQL Equivalent:
            SELECT * FROM accounts WHERE merchant_id = :merchant_id FOR UPDATE;

        CRITICAL NOTE:
        This lock remains active until the enclosing session commits or rolls back.
        If an external network request is made while this lock is held, all other
        concurrent callbacks for this merchant will block until timeout!
        """
        if not session.in_transaction:
            raise RuntimeError("Cannot acquire row lock outside active transaction")

        account = self._accounts.get(merchant_id)
        if not account:
            raise ValueError(f"Account for merchant_id {merchant_id} not found")

        lock_identifier = f"LOCK:account:merchant_id:{merchant_id}"
        session.held_locks.append(lock_identifier)
        logger.info(f"Acquired exclusive row lock: {lock_identifier} in session {id(session)}")
        return account

    def get_transaction_by_ref(self, session: DatabaseSession, tx_ref: str) -> Optional[TransactionModel]:
        """Fetch transaction record by reference key."""
        return self._transactions.get(tx_ref)

    def save_transaction(self, session: DatabaseSession, transaction: TransactionModel) -> TransactionModel:
        """Persist or update transaction record."""
        self._transactions[transaction.transaction_ref] = transaction
        logger.info(f"Persisted transaction {transaction.transaction_ref} with status {transaction.status}")
        return transaction

    def update_transaction_status(
        self, session: DatabaseSession, tx_ref: str, status: TransactionStatus, failure_reason: Optional[str] = None
    ) -> TransactionModel:
        """Update transaction status within active transaction."""
        tx = self._transactions.get(tx_ref)
        if not tx:
            raise ValueError(f"Transaction ref {tx_ref} not found")
        tx.status = status
        tx.failure_reason = failure_reason
        return tx

    def record_webhook_audit(self, session: DatabaseSession, audit: WebhookAuditLog) -> None:
        """Store immutable webhook receipt log."""
        self._audit_logs.append(audit)
        logger.info(f"Recorded webhook audit log {audit.id} for provider {audit.provider}")


# Global repository instance
payment_repository = PaymentRepository()
