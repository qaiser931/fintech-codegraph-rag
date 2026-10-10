"""JazzCash Mobile Wallet (MWALLET) callback notification endpoint.

RECEIVES:
Inbound HTTP POST webhook notifications from JazzCash servers following customer C2B transactions.

CALL PATH TO PLANTED ROOT CAUSE:
1. handle_jazzcash_callback
2. verify_webhook_signature (in auth.webhook_verification)
3. process_jazzcash_callback (in services.payment_service)
4. acquire_account_lock (in db.repository) -> ACQUIRES EXCLUSIVE ROW LOCK (SELECT FOR UPDATE)
5. verify_switch_transaction (in integrations.onelink_client) -> SLOW NETWORK CALL WHILE LOCK HELD
"""

from typing import Any, Dict
from fastapi import APIRouter, Header, HTTPException, Request
from data.sample_codebase.auth.webhook_verification import verify_webhook_signature
from data.sample_codebase.integrations.jazzcash_gateway import jazzcash_client
from data.sample_codebase.services.notification_service import notification_service
from data.sample_codebase.services.payment_service import payment_service
from data.sample_codebase.utils.logging import get_logger

logger = get_logger("routes.jazzcash_callback")

router = APIRouter(prefix="/api/v1/callbacks", tags=["Callbacks"])


@router.post("/jazzcash")
async def handle_jazzcash_callback(
    request: Request,
    x_jazzcash_signature: str = Header(default="", alias="X-JazzCash-Signature"),
) -> Dict[str, Any]:
    """Handle incoming payment callback notification from JazzCash MWALLET.

    Validates webhook authenticity, locks the merchant ledger row, verifies
    switch clearance via 1LINK, and dispatches customer notification.
    """
    raw_payload: Dict[str, str] = await request.json()
    headers_dict = dict(request.headers)

    logger.info(f"Received JazzCash callback with payload size {len(raw_payload)} keys")

    # Step 1: Cryptographic signature verification
    is_valid = verify_webhook_signature(
        headers=headers_dict,
        payload_dict=raw_payload,
        provider="JAZZCASH",
    )
    if not is_valid:
        logger.error("Unauthorized callback: JazzCash HMAC signature mismatch")
        raise HTTPException(status_code=401, detail="Invalid HMAC-SHA256 signature")

    # Step 2: Parse and normalize gateway payload
    normalized_data = jazzcash_client.parse_callback_payload(raw_payload)

    # Step 3: Process payment through core service (triggers row lock + 1LINK call)
    try:
        settlement_result = payment_service.process_jazzcash_callback(normalized_data)
    except Exception as exc:
        logger.error(f"Callback processing timeout or database lock failure: {exc}")
        raise HTTPException(
            status_code=504,
            detail="Transaction processing timed out acquiring merchant ledger lock",
        ) from exc

    # Step 4: Dispatch notification
    notification_service.send_payment_sms_alert(
        msisdn=raw_payload.get("pp_MobileNumber", "923000000000"),
        amount_pkr=str(normalized_data["amount"]),
        tx_ref=normalized_data["transaction_ref"],
    )

    return {
        "response_code": "00",
        "response_message": "Callback processed and settled successfully",
        "settlement": settlement_result,
    }
