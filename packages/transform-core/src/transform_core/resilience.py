"""
Resilience & Rate Limiting Utilities for Portfolio Integration
Provides exponential backoff with jitter and token bucket rate limiters
for robust network fetching across external financial APIs.
"""

import functools
import logging
import random
import time
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


class RateLimitExceeded(Exception):
    """Raised when rate limit is exceeded and cannot be satisfied."""


class RateLimiter:
    """
    Token-bucket rate limiter to prevent triggering HTTP 429s from external APIs.
    
    Example:
        limiter = RateLimiter(max_per_second=5.0)
        limiter.acquire()
    """

    def __init__(self, max_per_second: float = 5.0, burst: int | None = None):
        self.rate = max_per_second
        self.capacity = burst if burst is not None else max(1, int(max_per_second))
        self.tokens = float(self.capacity)
        self.last_check = time.monotonic()

    def acquire(self, tokens: int = 1) -> None:
        """Blocks until the requested number of tokens is available."""
        while True:
            now = time.monotonic()
            elapsed = now - self.last_check
            self.last_check = now

            # Replenish tokens
            self.tokens = min(float(self.capacity), self.tokens + elapsed * self.rate)

            if self.tokens >= tokens:
                self.tokens -= tokens
                return

            # Sleep until enough tokens are expected
            needed = tokens - self.tokens
            sleep_time = needed / self.rate
            time.sleep(max(0.01, sleep_time))

    def __enter__(self):
        self.acquire(1)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


def retry_with_backoff(
    max_attempts: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 15.0,
    backoff_factor: float = 2.0,
    jitter: bool = True,
    retry_exceptions: tuple[type[BaseException], ...] = (Exception,),
    on_retry: Callable[[Exception, int, float], None] | None = None,
):
    """
    Decorator for retrying a function with exponential backoff and optional jitter.
    
    Args:
        max_attempts: Maximum number of execution attempts before re-raising.
        initial_delay: Initial delay in seconds before the first retry.
        max_delay: Maximum ceiling cap for backoff delay.
        backoff_factor: Multiplier applied to delay after each failure.
        jitter: If True, adds random jitter between 0 and 50% of the current delay.
        retry_exceptions: Tuple of exception classes that trigger a retry.
        on_retry: Optional callback invoked as (exception, attempt_num, sleep_time).
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            attempt = 1
            current_delay = initial_delay

            while True:
                try:
                    return func(*args, **kwargs)
                except retry_exceptions as e:
                    if attempt >= max_attempts:
                        logger.error(
                            f"[{func.__name__}] Failed after {attempt} attempts: {e}"
                        )
                        raise

                    sleep_time = current_delay
                    if jitter:
                        sleep_time += random.uniform(0, 0.5 * current_delay)
                    sleep_time = min(sleep_time, max_delay)

                    if on_retry:
                        on_retry(e, attempt, sleep_time)
                    else:
                        logger.warning(
                            f"[{func.__name__}] Attempt {attempt}/{max_attempts} failed: {e}. "
                            f"Retrying in {sleep_time:.2f}s..."
                        )

                    time.sleep(sleep_time)
                    current_delay = min(current_delay * backoff_factor, max_delay)
                    attempt += 1

        return wrapper
    return decorator
