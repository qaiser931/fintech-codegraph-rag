"""Structured JSON logging for financial audit trails."""

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional


class StructuredJsonFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects with ISO8601 UTC timestamps."""

    def format(self, record: logging.LogRecord) -> str:
        log_payload: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "line": record.lineno,
        }
        if hasattr(record, "transaction_ref"):
            log_payload["transaction_ref"] = record.transaction_ref
        if hasattr(record, "merchant_id"):
            log_payload["merchant_id"] = record.merchant_id
        if record.exc_info:
            log_payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_payload)


def get_logger(name: str) -> logging.Logger:
    """Instantiate and configure a structured logger instance."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(StructuredJsonFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger
