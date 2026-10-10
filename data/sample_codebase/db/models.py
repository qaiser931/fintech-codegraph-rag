"""Data models representing Pakistani fintech banking ledgers and transactions."""

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class TransactionStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    REVERSED = "REVERSED"


class PaymentProvider(str, Enum):
    JAZZCASH = "JAZZCASH"
    EASYPAISA = "EASYPAISA"
    ONELINK = "ONELINK"


class AccountModel(BaseModel):
    """Merchant and customer balance ledger account."""
    id: int
    account_number: str
    merchant_id: str
    currency: str = "PKR"
    balance: Decimal = Decimal("0.00")
    locked_balance: Decimal = Decimal("0.00")
    is_active: bool = True
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TransactionModel(BaseModel):
    """Core payment transaction record."""
    id: int
    transaction_ref: str
    provider: PaymentProvider
    external_reference: Optional[str] = None
    account_id: int
    amount: Decimal
    fee: Decimal = Decimal("0.00")
    status: TransactionStatus = TransactionStatus.PENDING
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    failure_reason: Optional[str] = None


class WebhookAuditLog(BaseModel):
    """Immutable audit trail for incoming payment provider webhooks."""
    id: int
    provider: PaymentProvider
    payload_hash: str
    raw_payload: str
    signature: str
    is_verified: bool
    processed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class LedgerEntry(BaseModel):
    """Double-entry ledger journal record."""
    id: int
    transaction_id: int
    account_id: int
    entry_type: str  # DEBIT or CREDIT
    amount: Decimal
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
