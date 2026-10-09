"""Rate limiter -- token bucket algorithm for per-agent/per-tool throttling."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Optional, Tuple

__all__ = ["RateLimitConfig", "RateLimiter", "TokenBucket"]


@dataclass(slots=True)
class RateLimitConfig:
    """Configuration for rate limiting."""

    requests_per_minute: int = 60
    burst_size: int = 10  # max tokens in bucket
    enabled: bool = True


class TokenBucket:
    """Thread-safe token bucket for rate limiting."""

    def __init__(self, rate: float, capacity: int) -> None:
        self._rate = rate  # tokens per second
        self._capacity = capacity
        self._tokens = float(capacity)
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()

    def consume(self, tokens: int = 1) -> Tuple[bool, float]:
        """Try to consume tokens. Returns (allowed, wait_seconds)."""
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(
                self._capacity,
                self._tokens + elapsed * self._rate,
            )
            self._last_refill = now

            if self._tokens >= tokens:
                self._tokens -= tokens
                return True, 0.0
            else:
                wait = (tokens - self._tokens) / self._rate
                return False, wait

    @property
    def available(self) -> float:
        """Current available tokens (approximate)."""
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            return min(self._capacity, self._tokens + elapsed * self._rate)


class RateLimiter:
    """Rate limiter with per-key token buckets.

    Keys are typically "agent_id:tool_name" or just "agent_id".
    """

    def __init__(self, config: Optional[RateLimitConfig] = None) -> None:
        self._config = config or RateLimitConfig()

        # The Rust limiter when the extension is built, else its Python twin.
        from openjarvis._rust_bridge import get_native

        self._rust_impl = get_native("RateLimiter")(
            requests_per_minute=self._config.requests_per_minute,
            burst_size=self._config.burst_size,
        )

    def check(self, key: str) -> Tuple[bool, float]:
        """Check if a request is allowed for *key*: (allowed, seconds to wait)."""
        if not self._config.enabled:
            return True, 0.0
        return self._rust_impl.check(key)

    def reset(self, key: Optional[str] = None) -> None:
        """Reset rate limit state for a key, or for all keys."""
        self._rust_impl.reset(key)

    @property
    def config(self) -> RateLimitConfig:
        return self._config
