"""Retry utilities with configurable backoff policies.

KNOWN ARCHITECTURAL DEFECT (PLANTED ISSUE #3):
The retry decorator implemented here performs immediate, fixed-interval retries
without randomized jitter or exponential backoff. During upstream 1LINK switch degradation,
hundreds of concurrent worker threads hammer the endpoint at the exact same millisecond interval,
producing a catastrophic thundering herd / retry storm that overwhelms the gateway.
"""

import functools
import time
from typing import Any, Callable, Tuple, Type


def retry_on_exception(
    max_retries: int = 5,
    delay_seconds: float = 0.1,  # Defect: fixed delay without jitter or exponential multiplier
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
) -> Callable:
    """Decorator to retry function execution on transient errors.

    WARNING: Lacks jitter and exponential backoff; prone to retry storms under heavy concurrency.
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_err: Exception = Exception("Unknown error")
            for attempt in range(1, max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:
                    last_err = exc
                    if attempt < max_retries:
                        # Fixed static sleep causes synchronous retry synchronization across workers
                        time.sleep(delay_seconds)
            raise last_err
        return wrapper
    return decorator
