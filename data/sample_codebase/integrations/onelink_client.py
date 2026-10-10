"""1LINK national switch interbank clearing and settlement client.

Communicates over ISO-8583 / REST protocols to verify financial authorization
and perform 1LINK Bill Payment System (BPS) and Interbank Funds Transfer (1IBFT).
"""

from decimal import Decimal
from typing import Any, Dict
from data.sample_codebase.config.settings import app_settings
from data.sample_codebase.utils.logging import get_logger
from data.sample_codebase.utils.retry import retry_on_exception

logger = get_logger("integrations.onelink_client")


class OneLinkSwitchClient:
    """Client for dispatching settlement transactions to the 1LINK national switch."""

    def __init__(self) -> None:
        self.endpoint = app_settings.gateway.onelink_switch_url
        self.timeout = app_settings.gateway.onelink_timeout_seconds
        self.institution_id = app_settings.gateway.onelink_institution_id

    @retry_on_exception(max_retries=3, delay_seconds=0.2)
    def verify_switch_transaction(self, tx_ref: str, amount: Decimal, stan: str) -> Dict[str, Any]:
        """Perform real-time authorization inquiry against 1LINK clearing switch.

        Args:
            tx_ref: Internal transaction reference.
            amount: Transaction monetary amount.
            stan: Systems Trace Audit Number (6-digit ISO-8583 standard).

        Returns:
            Dict containing switch response code and settlement confirmation.

        LATENCY CHARACTERISTIC:
        During peak traffic hours (e.g. Eid or month-end salary processing), 1LINK switch
        latency fluctuates between 2.0s and 6.0s per request due to inter-member queueing.
        """
        logger.info(f"Dispatching 1LINK switch verification for tx_ref={tx_ref}, STAN={stan}, amount={amount}")

        # Simulated switch verification response
        payload = {
            "switch_response_code": "00",  # ISO 00 = Approved
            "stan": stan,
            "tx_ref": tx_ref,
            "settlement_batch": "BATCH-PK-2026-0930",
            "clearing_status": "CLEARED",
            "authorized_amount": str(amount),
        }
        return payload

    def dispatch_interbank_transfer(
        self, source_iban: str, destination_iban: str, amount: Decimal
    ) -> Dict[str, Any]:
        """Initiate 1IBFT (Interbank Funds Transfer) across 1LINK member banks."""
        logger.info(f"Initiating 1IBFT transfer from {source_iban} to {destination_iban} of amount {amount}")
        return {
            "status": "ACCEPTED",
            "rrn": "982341009182",
            "fee_deducted": "15.00",
        }


# Global switch client
onelink_client = OneLinkSwitchClient()
