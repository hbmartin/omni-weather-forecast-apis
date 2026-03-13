from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager


class TokenBucketRateLimiter:
    """
    Async token-bucket rate limiter.

    Tokens refill at a fixed rate. Every acquisition consumes one token.
    """

    def __init__(self, rate: float, max_tokens: int | None = None) -> None:
        if rate <= 0:
            raise ValueError("rate must be positive")
        resolved_max_tokens = (
            max(1, int(rate * 2)) if max_tokens is None else max_tokens
        )
        if resolved_max_tokens <= 0:
            raise ValueError("max_tokens must be positive")
        self._rate = rate
        self._max_tokens = resolved_max_tokens
        self._tokens = float(self._max_tokens)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Acquire one token, waiting until one is available."""

        while True:
            async with self._lock:
                self._refill()
                if self._tokens >= 1:
                    self._tokens -= 1
                    return
            await asyncio.sleep(1.0 / self._rate)

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._max_tokens, self._tokens + (elapsed * self._rate))
        self._last_refill = now


class CompositeRateLimiter:
    """Combine a global concurrency gate with optional token buckets."""

    def __init__(
        self,
        semaphore: asyncio.Semaphore,
        *buckets: TokenBucketRateLimiter | None,
    ) -> None:
        self._semaphore = semaphore
        self._buckets = tuple(bucket for bucket in buckets if bucket is not None)

    @asynccontextmanager
    async def slot(self) -> AsyncGenerator[None, None]:
        """Acquire all configured limiter primitives."""

        async with self._semaphore:
            for bucket in self._buckets:
                await bucket.acquire()
            yield
