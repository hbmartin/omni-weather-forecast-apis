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


def test_composite_rate_limiter_waits_for_semaphore_before_buckets() -> None:
    class RecordingBucket(TokenBucketRateLimiter):
        def __init__(self) -> None:
            super().__init__(rate=1, max_tokens=1)
            self.calls = 0

        async def acquire(self) -> None:
            self.calls += 1

    async def scenario() -> tuple[int, int]:
        bucket = RecordingBucket()
        semaphore = asyncio.Semaphore(0)
        limiter = CompositeRateLimiter(semaphore, bucket)
        task = asyncio.create_task(_consume_slot(limiter))
        await asyncio.sleep(0.01)
        calls_while_blocked = bucket.calls
        semaphore.release()
        await asyncio.wait_for(task, timeout=0.1)
        return calls_while_blocked, bucket.calls

    async def _consume_slot(limiter: CompositeRateLimiter) -> None:
        async with limiter.slot():
            return

    calls_while_blocked, total_calls = asyncio.run(scenario())

    assert calls_while_blocked == 0
    assert total_calls == 1
