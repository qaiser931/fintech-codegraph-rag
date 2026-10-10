"""Merchant fund disbursement and IBFT transfer endpoint."""

from decimal import Decimal
from typing import Any, Dict
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from data.sample_codebase.integrations.onelink_client import onelink_client
from data.sample_codebase.utils.logging import get_logger

logger = get_logger("routes.disbursement")

router = APIRouter(prefix="/api/v1/disbursement", tags=["Disbursement"])


class DisbursementRequest(BaseModel):
    source_iban: str
    destination_iban: str
    amount: Decimal
    purpose: str = "MERCHANT_SETTLEMENT"


@router.post("/ibft")
async def initiate_disbursement(payload: DisbursementRequest) -> Dict[str, Any]:
    """Execute interbank fund disbursement via 1LINK switch."""
    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail="Disbursement amount must be positive")

    logger.info(f"Executing disbursement of PKR {payload.amount} to IBAN {payload.destination_iban}")
    result = onelink_client.dispatch_interbank_transfer(
        source_iban=payload.source_iban,
        destination_iban=payload.destination_iban,
        amount=payload.amount,
    )
    return {
        "status": "COMPLETED",
        "switch_response": result,
    }
