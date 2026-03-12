"""Token-bucket rate limiter for async operations."""

import asyncio
import time


class TokenBucketRateLimiter:
    """Async token-bucket rate limiter.

    Tokens are added at a fixed rate. Each request consumes one token.
    If no tokens are available, the caller awaits until one is
    replenished.
    """

    def __init__(self, rate: float, max_tokens: int | None = None) -> None:
        self._rate = rate
        self._max_tokens = max_tokens or max(int(rate * 2), 1)
        self._tokens = float(self._max_tokens)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Acquire one token. Awaits if bucket is empty."""
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
        self._tokens = min(self._max_tokens, self._tokens + elapsed * self._rate)
        self._last_refill = now
