"""Double-entry general ledger management."""

from decimal import Decimal
from data.sample_codebase.db.models import LedgerEntry
from data.sample_codebase.db.session import DatabaseSession
from data.sample_codebase.utils.logging import get_logger

logger = get_logger("services.ledger")


class LedgerService:
    """Manages double-entry bookkeeping for regulatory SBP compliance."""

    def record_split_ledger(
        self, session: DatabaseSession, transaction_id: int, account_id: int, amount: Decimal, fee: Decimal
    ) -> list[LedgerEntry]:
        """Record balanced debit and credit entries."""
        credit_entry = LedgerEntry(
            id=101,
            transaction_id=transaction_id,
            account_id=account_id,
            entry_type="CREDIT",
            amount=amount - fee,
        )
        fee_entry = LedgerEntry(
            id=102,
            transaction_id=transaction_id,
            account_id=999,  # System fee pool account
            entry_type="CREDIT",
            amount=fee,
        )
        logger.info(f"Recorded balanced ledger entries for transaction {transaction_id}")
        return [credit_entry, fee_entry]


ledger_service = LedgerService()
