"""
Unit tests for resilience and rate limiting utilities.
"""

import time

import pytest
from transform_core.resilience import RateLimiter, retry_with_backoff


def test_retry_with_backoff_success():
    call_count = 0

    @retry_with_backoff(max_attempts=3, initial_delay=0.01, max_delay=0.1)
    def flappy_func():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ConnectionError("Transient network failure")
        return "success"

    result = flappy_func()
    assert result == "success"
    assert call_count == 3


def test_retry_with_backoff_exhaustion():
    call_count = 0

    @retry_with_backoff(max_attempts=2, initial_delay=0.01, max_delay=0.05)
    def permanent_fail():
        nonlocal call_count
        call_count += 1
        raise ValueError("Permanent failure")

    with pytest.raises(ValueError, match="Permanent failure"):
        permanent_fail()
    assert call_count == 2


def test_rate_limiter_throttling():
    limiter = RateLimiter(max_per_second=20.0, burst=2)
    start = time.monotonic()
    
    for _ in range(4):
        limiter.acquire(1)
        
    duration = time.monotonic() - start
    # At 20/sec with burst 2, 4 requests should take around 0.1s
    assert duration >= 0.05
