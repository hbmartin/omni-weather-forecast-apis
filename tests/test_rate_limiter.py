"""Tests for rate limiter."""

import asyncio
import time

import pytest

from omni_weather_forecast_apis.rate_limiter import TokenBucketRateLimiter


class TestTokenBucketRateLimiter:
    @pytest.mark.asyncio
    async def test_immediate_acquire(self):
        limiter = TokenBucketRateLimiter(rate=100.0)
        start = time.monotonic()
        await limiter.acquire()
        elapsed = time.monotonic() - start
        assert elapsed < 0.1

    @pytest.mark.asyncio
    async def test_multiple_acquires(self):
        limiter = TokenBucketRateLimiter(rate=100.0, max_tokens=5)
        for _ in range(5):
            await limiter.acquire()

    @pytest.mark.asyncio
    async def test_rate_limiting_blocks(self):
        limiter = TokenBucketRateLimiter(rate=2.0, max_tokens=1)
        await limiter.acquire()
        start = time.monotonic()
        await limiter.acquire()
        elapsed = time.monotonic() - start
        assert elapsed >= 0.3
