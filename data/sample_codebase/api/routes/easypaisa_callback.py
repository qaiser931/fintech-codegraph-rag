"""EasyPaisa Mobile Account callback webhook endpoint.

KNOWN ARCHITECTURAL DEFECT (PLANTED ISSUE #4):
Duplicate Callback Race Condition / Lack of Idempotency Guard.
When EasyPaisa retries callback POST requests due to transient upstream network delays,
this route executes processing without first checking if the transaction was already
marked SUCCESS or in-flight in a state machine.
This permits duplicate credit processing on simultaneous retry callbacks.
"""

from typing import Any, Dict
from fastapi import APIRouter, Header, HTTPException, Request
from data.sample_codebase.auth.webhook_verification import verify_webhook_signature
from data.sample_codebase.integrations.easypaisa_gateway import easypaisa_client
from data.sample_codebase.services.notification_service import notification_service
from data.sample_codebase.utils.logging import get_logger

logger = get_logger("routes.easypaisa_callback")

router = APIRouter(prefix="/api/v1/callbacks", tags=["Callbacks"])


@router.post("/easypaisa")
async def handle_easypaisa_callback(
    request: Request,
    x_easypaisa_digest: str = Header(default="", alias="X-EasyPaisa-Digest"),
) -> Dict[str, Any]:
    """Process incoming EasyPaisa MA payment notifications.

    ARCHITECTURAL FLAW:
    Missing idempotency check! Does not query transaction status prior to credit action.
    """
    raw_payload: Dict[str, str] = await request.json()
    headers_dict = dict(request.headers)

    # Validate signature
    is_valid = verify_webhook_signature(
        headers=headers_dict,
        payload_dict=raw_payload,
        provider="EASYPAISA",
    )
    if not is_valid:
        raise HTTPException(status_code=401, detail="Invalid EasyPaisa HMAC digest")

    parsed = easypaisa_client.parse_callback_payload(raw_payload)

    # CRITICAL BUG: No check whether parsed["transaction_ref"] has already been credited!
    logger.warning(
        f"Processing EasyPaisa callback for ref={parsed['transaction_ref']} without idempotency guard"
    )

    # Dispatch notification directly without checking prior state
    notification_service.send_payment_sms_alert(
        msisdn=raw_payload.get("msisdn", "923450000000"),
        amount_pkr=str(parsed["amount"]),
        tx_ref=parsed["transaction_ref"],
    )

    return {
        "status": "0000",
        "desc": "Callback received and recorded",
        "order_id": parsed["order_id"],
    }
