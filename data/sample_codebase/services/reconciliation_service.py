"""Daily batch reconciliation and settlement verification service."""

from typing import Any, Dict, List
from data.sample_codebase.db.models import TransactionStatus
from data.sample_codebase.db.session import get_db_session
from data.sample_codebase.integrations.onelink_client import onelink_client
from data.sample_codebase.utils.logging import get_logger
from data.sample_codebase.utils.retry import retry_on_exception

logger = get_logger("services.reconciliation")


class ReconciliationService:
    """Reconciles internal transaction records against 1LINK daily settlement files."""

    @retry_on_exception(max_retries=5, delay_seconds=0.1)
    def reconcile_batch(self, batch_id: str, transactions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Perform batch comparison against 1LINK clearing house records.

        VULNERABILITY TO RETRY STORM:
        Uses `retry_on_exception` with fixed delay (0.1s) and no jitter.
        When 1LINK is experiencing 503 Service Unavailable, this method retries 5 times in rapid
        succession across parallel reconciliation workers, producing a retry storm.
        """
        logger.info(f"Reconciling settlement batch {batch_id} containing {len(transactions)} transactions")

        reconciled_count = 0
        discrepancies: List[str] = []

        with get_db_session() as session:
            for tx in transactions:
                # Simulating batch item check
                if tx.get("status") == TransactionStatus.SUCCESS.value:
                    reconciled_count += 1
                else:
                    discrepancies.append(tx.get("transaction_ref", "UNKNOWN"))

        return {
            "batch_id": batch_id,
            "total_items": len(transactions),
            "reconciled_count": reconciled_count,
            "discrepancies": discrepancies,
            "reconciliation_status": "MATCHED" if not discrepancies else "DISCREPANCY_DETECTED",
        }


reconciliation_service = ReconciliationService()
