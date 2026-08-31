"""A small fixed-window rate limiter.

In-process and therefore per-worker: with N workers the effective limit is N
times higher. That is a real limitation, not a hidden one -- it is written here
and in the backend README, and the fix is a shared counter (Redis) behind the
same interface.

Even so it is worth having: it turns unlimited online password guessing into a
few attempts per minute, which is the difference that matters.
"""

from __future__ import annotations

import time
from collections import defaultdict


class RateLimiter:
    def __init__(self, limit: int, window_seconds: float) -> None:
        self._limit = limit
        self._window = window_seconds
        self._hits: dict[str, list[float]] = defaultdict(list)

    def check(self, key: str, now: float | None = None) -> bool:
        """Record an attempt. False means the caller is over the limit."""
        current = now if now is not None else time.monotonic()
        cutoff = current - self._window

        recent = [t for t in self._hits[key] if t > cutoff]
        recent.append(current)
        self._hits[key] = recent

        if len(self._hits) > 10_000:
            self._evict(cutoff)

        return len(recent) <= self._limit

    def reset(self, key: str) -> None:
        """Forget a key -- called after a successful login."""
        self._hits.pop(key, None)

    def _evict(self, cutoff: float) -> None:
        """Drop keys with no recent activity so the map cannot grow unbounded."""
        stale = [k for k, times in self._hits.items() if not any(t > cutoff for t in times)]
        for key in stale:
            del self._hits[key]


login_limiter = RateLimiter(limit=8, window_seconds=300)
"""Eight attempts per five minutes, keyed by client address and email."""
