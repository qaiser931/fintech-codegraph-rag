"""Customer SMS and webhook dispatch notification service."""

from typing import Dict
from data.sample_codebase.utils.logging import get_logger

logger = get_logger("services.notification")


class NotificationService:
    """Dispatches transaction SMS alerts and merchant push notifications."""

    def send_payment_sms_alert(self, msisdn: str, amount_pkr: str, tx_ref: str) -> bool:
        """Send Urdu/English bilingual transactional SMS alert to customer."""
        logger.info(f"Dispatching SMS to {msisdn}: Payment of PKR {amount_pkr} successful. Ref: {tx_ref}")
        return True

    def notify_merchant_webhook(self, webhook_url: str, event_data: Dict[str, str]) -> bool:
        """Post merchant asynchronous notification."""
        logger.info(f"Dispatched webhook notification to {webhook_url} for event {event_data.get('event')}")
        return True


notification_service = NotificationService()
