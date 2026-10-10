"""JazzCash Mobile Wallet (MWALLET) API integration gateway."""

from decimal import Decimal
from typing import Any, Dict
from data.sample_codebase.config.settings import app_settings
from data.sample_codebase.utils.logging import get_logger

logger = get_logger("integrations.jazzcash")


class JazzCashGatewayClient:
    """Client for initiating and processing JazzCash mobile wallet transactions."""

    def __init__(self) -> None:
        self.base_url = app_settings.gateway.jazzcash_base_url
        self.merchant_id = app_settings.gateway.jazzcash_merchant_id
        self.timeout = app_settings.gateway.jazzcash_timeout_seconds

    def parse_callback_payload(self, raw_post_data: Dict[str, str]) -> Dict[str, Any]:
        """Normalize JazzCash C2B callback payload into standardized internal dictionary."""
        return {
            "transaction_ref": raw_post_data.get("pp_TxnRefNo", ""),
            "amount": Decimal(raw_post_data.get("pp_Amount", "0.00")) / Decimal("100"),
            "response_code": raw_post_data.get("pp_ResponseCode", ""),
            "response_message": raw_post_data.get("pp_ResponseMessage", ""),
            "stan": raw_post_data.get("pp_RetreivalReferenceNo", "000000"),
            "merchant_id": raw_post_data.get("pp_MerchantID", self.merchant_id),
            "bank_id": raw_post_data.get("pp_BankID", "JAZZ"),
        }


# Global JazzCash gateway instance
jazzcash_client = JazzCashGatewayClient()
