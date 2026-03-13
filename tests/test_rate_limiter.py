from __future__ import annotations

import asyncio
import time

from omni_weather_forecast_apis.rate_limiter import (
    CompositeRateLimiter,
    TokenBucketRateLimiter,
)


def test_token_bucket_waits_for_refill() -> None:
    async def scenario() -> float:
        limiter = TokenBucketRateLimiter(rate=2, max_tokens=1)
        started_at = time.perf_counter()
        await limiter.acquire()
        await limiter.acquire()
        return time.perf_counter() - started_at

    elapsed = asyncio.run(scenario())

    assert elapsed >= 0.45


def test_composite_rate_limiter_serializes_on_semaphore() -> None:
    async def scenario() -> int:
        limiter = CompositeRateLimiter(
            asyncio.Semaphore(1),
            TokenBucketRateLimiter(rate=100, max_tokens=100),
        )
        active = 0
        peak = 0

        async def worker() -> None:
            nonlocal active, peak
            async with limiter.slot():
                active += 1
                peak = max(peak, active)
                await asyncio.sleep(0.01)
                active -= 1

        await asyncio.gather(*(worker() for _ in range(3)))
        return peak

    peak_active = asyncio.run(scenario())

    assert peak_active == 1
