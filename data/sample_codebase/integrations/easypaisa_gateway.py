"""EasyPaisa Open API payment gateway integration.

KNOWN ARCHITECTURAL DEFECT (PLANTED ISSUE #2):
The method `inquire_transaction_status` performs a direct socket network call
without specifying any request timeout (`timeout=None`).
When EasyPaisa servers experience latency spikes or packet loss, the calling
FastAPI worker thread hangs indefinitely, causing thread pool exhaustion.
"""

from decimal import Decimal
from typing import Any, Dict
from data.sample_codebase.config.settings import app_settings
from data.sample_codebase.utils.logging import get_logger

logger = get_logger("integrations.easypaisa")


class EasyPaisaGatewayClient:
    """Client for EasyPaisa mobile account payment interactions."""

    def __init__(self) -> None:
        self.base_url = app_settings.gateway.easypaisa_base_url
        self.store_id = app_settings.gateway.easypaisa_store_id

    def inquire_transaction_status(self, order_id: str) -> Dict[str, Any]:
        """Query transaction status directly from EasyPaisa settlement servers.

        CRITICAL BUG:
        Notice there is NO timeout configured on this socket call!
        If EasyPaisa gateway stalls, this thread blocks forever without failing fast.
        """
        logger.info(f"Querying EasyPaisa order {order_id} WITHOUT timeout limit")

        # In production code, this represents: requests.post(url, json=data) without timeout!
        # Simulation of network call lacking socket timeout:
        simulated_response = {
            "order_id": order_id,
            "status": "PAID",
            "transaction_id": "EP_TXN_9918231",
            "amount": "1500.00",
        }
        return simulated_response

    def parse_callback_payload(self, raw_params: Dict[str, str]) -> Dict[str, Any]:
        """Normalize EasyPaisa MA callback parameters."""
        return {
            "order_id": raw_params.get("orderId", ""),
            "transaction_ref": raw_params.get("transactionId", ""),
            "status": raw_params.get("status", ""),
            "amount": Decimal(raw_params.get("amount", "0.00")),
            "store_id": raw_params.get("storeId", self.store_id),
        }


# Global EasyPaisa gateway instance
easypaisa_client = EasyPaisaGatewayClient()
