"""Payment transaction inquiry and status check endpoint."""

from typing import Any, Dict
from fastapi import APIRouter, HTTPException
from data.sample_codebase.db.repository import payment_repository
from data.sample_codebase.db.session import get_db_session
from data.sample_codebase.utils.logging import get_logger

logger = get_logger("routes.payment_status")

router = APIRouter(prefix="/api/v1/payments", tags=["Payments"])


@router.get("/{tx_ref}")
async def get_payment_status(tx_ref: str) -> Dict[str, Any]:
    """Retrieve current processing status and details for a payment transaction."""
    logger.info(f"Querying status for transaction reference: {tx_ref}")

    with get_db_session() as session:
        tx = payment_repository.get_transaction_by_ref(session, tx_ref)
        if not tx:
            raise HTTPException(status_code=404, detail=f"Transaction {tx_ref} not found")

        return {
            "transaction_ref": tx.transaction_ref,
            "provider": tx.provider.value,
            "status": tx.status.value,
            "amount": str(tx.amount),
            "created_at": tx.created_at.isoformat(),
            "failure_reason": tx.failure_reason,
        }
