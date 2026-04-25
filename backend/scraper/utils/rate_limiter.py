import asyncio
import time
from collections import defaultdict


class RateLimiter:
    """Token bucket rate limiter per domain."""

    def __init__(self, requests_per_minute: int = 20):
        self._rpm = requests_per_minute
        self._interval = 60.0 / requests_per_minute
        self._last_request: dict[str, float] = defaultdict(float)
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def acquire(self, domain: str) -> None:
        async with self._locks[domain]:
            now = time.monotonic()
            elapsed = now - self._last_request[domain]
            if elapsed < self._interval:
                await asyncio.sleep(self._interval - elapsed)
            self._last_request[domain] = time.monotonic()
