"""Token bucket rate-limiting middleware — middleware stage #3.

Protects against brute-force attacks and resource exhaustion by enforcing
per-IP request budgets using a token bucket algorithm.

Two tiers:
    auth     — stricter limit (default 10 req/min) for authentication paths
    general  — standard limit (default 100 req/min) for all other paths

The in-memory bucket store is suitable for single-process deployments.
State is lost on process restart — this is acceptable for the hackathon
deployment target.

Token bucket algorithm:
    Each (client_ip, tier) pair owns a bucket that starts full.
    On every request, elapsed time is used to refill tokens proportionally
    (refill_rate = max_tokens / window_seconds).  One token is consumed per
    request.  If no token is available, HTTP 429 is returned immediately with
    Retry-After set to the seconds until the next token is available.

Thread safety:
    asyncio.Lock serialises all bucket reads/writes since FastAPI runs in a
    single event loop.  The lock is held only for bucket arithmetic, not for
    I/O, so it adds negligible latency.

Eviction:
    Expired buckets (not accessed within 2× window) are removed lazily on
    roughly 1% of requests to bound memory growth.
"""

from __future__ import annotations

import asyncio
import json
import random
import time
from dataclasses import dataclass, field
from typing import Any

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from forgeguard.core.config import get_settings

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Token bucket data structure
# ---------------------------------------------------------------------------

@dataclass
class TokenBucket:
    """Token bucket tracking consumed capacity for one (ip, tier) pair."""

    tokens: float
    max_tokens: int
    refill_rate: float          # tokens per second
    last_refill: float          # monotonic timestamp of last refill
    last_accessed: float = field(default_factory=time.monotonic)

    def refill(self) -> None:
        """Add tokens proportional to elapsed time, capped at max_tokens."""
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(float(self.max_tokens), self.tokens + elapsed * self.refill_rate)
        self.last_refill = now
        self.last_accessed = now

    def consume(self) -> tuple[bool, int]:
        """Try to consume one token.

        Returns:
            (True, 0)           — request is allowed
            (False, retry_after) — request is denied; retry_after is seconds
                                   until at least one token is available
        """
        self.refill()
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True, 0
        # Fractional tokens remain — calculate wait time for next full token.
        seconds_needed = (1.0 - self.tokens) / self.refill_rate
        retry_after = max(1, int(seconds_needed) + 1)
        return False, retry_after


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

class RateLimiterMiddleware(BaseHTTPMiddleware):
    """Per-IP token bucket rate limiting at middleware stage #3.

    Constructor kwargs override the values from :class:`~forgeguard.core.config.Settings`,
    making the middleware easy to configure in tests without environment variables.

    Args:
        app:             The next ASGI application in the stack.
        general_limit:   Override for ``settings.rate_limit_general``.
        auth_limit:      Override for ``settings.rate_limit_auth``.
        window_seconds:  Override for ``settings.rate_limit_window_seconds``.
        auth_paths:      Override for ``settings.rate_limit_auth_paths``.
    """

    def __init__(
        self,
        app: Any,
        general_limit: int | None = None,
        auth_limit: int | None = None,
        window_seconds: int | None = None,
        auth_paths: list[str] | None = None,
    ) -> None:
        super().__init__(app)
        settings = get_settings()
        self._general_limit: int = general_limit if general_limit is not None else settings.rate_limit_general
        self._auth_limit: int = auth_limit if auth_limit is not None else settings.rate_limit_auth
        self._window_seconds: int = window_seconds if window_seconds is not None else settings.rate_limit_window_seconds
        self._auth_paths: list[str] = auth_paths if auth_paths is not None else settings.rate_limit_auth_paths
        self._buckets: dict[tuple[str, str], TokenBucket] = {}
        self._lock: asyncio.Lock = asyncio.Lock()

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _get_client_ip(self, request: Request) -> str:
        """Extract the original client IP, honouring X-Forwarded-For."""
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            candidate = forwarded_for.split(",")[0].strip()
            if candidate:
                return candidate
        client = request.client
        if client and client.host:
            return client.host
        return "unknown"

    def _get_tier(self, path: str) -> str:
        """Classify the path as 'auth' or 'general'."""
        for prefix in self._auth_paths:
            if path.startswith(prefix):
                return "auth"
        return "general"

    def _make_bucket(self, tier: str) -> TokenBucket:
        """Create a full token bucket for the given tier."""
        max_tokens = self._auth_limit if tier == "auth" else self._general_limit
        refill_rate = max_tokens / self._window_seconds
        return TokenBucket(
            tokens=float(max_tokens),
            max_tokens=max_tokens,
            refill_rate=refill_rate,
            last_refill=time.monotonic(),
        )

    def _evict_expired(self) -> int:
        """Remove buckets idle for more than 2× the window period.

        Returns the number of evicted buckets (useful for testing).
        Called while the lock is held.
        """
        ttl = self._window_seconds * 2
        now = time.monotonic()
        expired = [
            key
            for key, bucket in self._buckets.items()
            if (now - bucket.last_accessed) > ttl
        ]
        for key in expired:
            del self._buckets[key]
        return len(expired)

    def _build_429_response(self, request_id: str | None, retry_after: int) -> Response:
        body = {
            "error": "rate_limit_exceeded",
            "message": f"Too many requests. Please retry after {retry_after} seconds.",
            "reference_id": request_id,
            "retry_after": retry_after,
        }
        return Response(
            content=json.dumps(body),
            status_code=429,
            headers={
                "Content-Type": "application/json",
                "Retry-After": str(retry_after),
            },
        )

    # ------------------------------------------------------------------ #
    # Dispatch
    # ------------------------------------------------------------------ #

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        # OPTIONS preflight requests must not consume tokens (CORS compliance).
        if request.method == "OPTIONS":
            return await call_next(request)

        ip = self._get_client_ip(request)
        tier = self._get_tier(request.url.path)
        key = (ip, tier)

        try:
            async with self._lock:
                # Lazy eviction: run on ~1% of requests to bound memory growth.
                if random.randint(1, 100) == 1:  # noqa: S311
                    self._evict_expired()

                bucket = self._buckets.get(key)
                if bucket is None:
                    bucket = self._make_bucket(tier)
                    self._buckets[key] = bucket

                allowed, retry_after = bucket.consume()

        except Exception as exc:
            # Fail-open: rate limiting must never block a legitimate request
            # due to its own internal error.
            logger.warning("rate_limiter_error", error=str(exc), path=request.url.path)
            return await call_next(request)

        if not allowed:
            request_id: str | None = getattr(request.state, "request_id", None)
            logger.info(
                "rate_limit_exceeded",
                client_ip=ip,
                tier=tier,
                path=request.url.path,
                retry_after=retry_after,
            )
            return self._build_429_response(request_id, retry_after)

        return await call_next(request)
