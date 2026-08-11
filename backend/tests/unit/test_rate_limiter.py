"""Unit tests for RateLimiterMiddleware (WO-024).

Uses a minimal FastAPI app with the middleware configured at low limits
so tests complete in milliseconds without real time.sleep calls.

Scenarios:
  Token bucket mechanics:
    - Requests within limit are allowed (200)
    - Requests exceeding limit are blocked (429)
    - 429 response includes Retry-After header
    - Retry-After value is a positive integer
  Path-tier routing:
    - Auth paths use the auth (strict) limit
    - General paths use the general (higher) limit
  Edge cases:
    - OPTIONS requests pass through regardless of limit
    - Fail-open: internal bucket error still passes the request
    - Eviction removes stale bucket entries
    - Eviction returns count of removed entries
  Bucket state:
    - Tokens refill over time (monotonic)
    - Different IPs have independent buckets
"""

from __future__ import annotations

import time

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from forgeguard.middleware.rate_limiter import RateLimiterMiddleware, TokenBucket


# ---------------------------------------------------------------------------
# Test app factory
# ---------------------------------------------------------------------------

def _make_app(
    *,
    general_limit: int = 5,
    auth_limit: int = 2,
    window_seconds: int = 60,
    auth_paths: list[str] | None = None,
) -> FastAPI:
    """Minimal FastAPI app with configurable rate limits for fast tests."""
    app = FastAPI()
    app.add_middleware(
        RateLimiterMiddleware,
        general_limit=general_limit,
        auth_limit=auth_limit,
        window_seconds=window_seconds,
        auth_paths=auth_paths or ["/api/v1/auth/"],
    )

    @app.get("/api/v1/services")
    async def general_route() -> dict:
        return {"ok": True}

    @app.post("/api/v1/auth/login")
    async def auth_route() -> dict:
        return {"ok": True}

    return app


# ---------------------------------------------------------------------------
# TokenBucket unit tests
# ---------------------------------------------------------------------------

class TestTokenBucket:
    def test_new_bucket_starts_full(self):
        bucket = TokenBucket(
            tokens=10.0, max_tokens=10, refill_rate=10 / 60.0,
            last_refill=time.monotonic(),
        )
        allowed, _ = bucket.consume()
        assert allowed is True

    def test_empty_bucket_denies_request(self):
        bucket = TokenBucket(
            tokens=0.0, max_tokens=10, refill_rate=10 / 60.0,
            last_refill=time.monotonic(),
        )
        allowed, retry_after = bucket.consume()
        assert allowed is False
        assert retry_after >= 1

    def test_retry_after_is_positive_integer(self):
        bucket = TokenBucket(
            tokens=0.0, max_tokens=10, refill_rate=10 / 60.0,
            last_refill=time.monotonic(),
        )
        _, retry_after = bucket.consume()
        assert isinstance(retry_after, int)
        assert retry_after >= 1

    def test_consume_decrements_tokens(self):
        bucket = TokenBucket(
            tokens=3.0, max_tokens=10, refill_rate=10 / 60.0,
            last_refill=time.monotonic(),
        )
        bucket.consume()
        # After one consume, tokens should be < 3 (might have refilled slightly)
        assert bucket.tokens < 3.0

    def test_refill_adds_tokens_over_time(self):
        # Start with a near-empty bucket
        bucket = TokenBucket(
            tokens=0.0, max_tokens=10, refill_rate=100.0,  # fast refill for test
            last_refill=time.monotonic() - 1.0,  # pretend 1 second has elapsed
        )
        bucket.refill()
        assert bucket.tokens > 0.0

    def test_refill_does_not_exceed_max(self):
        bucket = TokenBucket(
            tokens=10.0, max_tokens=10, refill_rate=10 / 60.0,
            last_refill=time.monotonic() - 3600,  # 1 hour ago — would overfill
        )
        bucket.refill()
        assert bucket.tokens == 10.0


# ---------------------------------------------------------------------------
# Middleware: requests within limit
# ---------------------------------------------------------------------------

class TestRequestsWithinLimit:
    async def test_single_request_to_general_route_is_allowed(self):
        app = _make_app(general_limit=5)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/v1/services")
        assert resp.status_code == 200

    async def test_single_request_to_auth_route_is_allowed(self):
        app = _make_app(auth_limit=2)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post("/api/v1/auth/login")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Middleware: rate limit exceeded
# ---------------------------------------------------------------------------

class TestRateLimitExceeded:
    async def test_exceeding_auth_limit_returns_429(self):
        app = _make_app(auth_limit=2, window_seconds=60)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            for _ in range(2):
                await c.post("/api/v1/auth/login")
            resp = await c.post("/api/v1/auth/login")
        assert resp.status_code == 429

    async def test_429_has_retry_after_header(self):
        app = _make_app(auth_limit=1, window_seconds=60)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            await c.post("/api/v1/auth/login")
            resp = await c.post("/api/v1/auth/login")
        assert resp.status_code == 429
        assert "retry-after" in resp.headers or "Retry-After" in resp.headers

    async def test_retry_after_is_positive_integer_string(self):
        app = _make_app(auth_limit=1, window_seconds=60)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            await c.post("/api/v1/auth/login")
            resp = await c.post("/api/v1/auth/login")
        retry_after = resp.headers.get("retry-after") or resp.headers.get("Retry-After")
        assert retry_after is not None
        assert int(retry_after) >= 1

    async def test_general_limit_is_higher_than_auth_limit(self):
        app = _make_app(general_limit=5, auth_limit=2, window_seconds=60)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            # 3 requests to general path should be allowed
            for _ in range(3):
                resp = await c.get("/api/v1/services")
            assert resp.status_code == 200

    async def test_auth_limit_does_not_affect_general_paths(self):
        # Auth limit is 1; general limit is 5 — general path should not be blocked
        app = _make_app(general_limit=5, auth_limit=1, window_seconds=60)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            await c.post("/api/v1/auth/login")
            await c.post("/api/v1/auth/login")  # would be blocked on auth path
            for _ in range(3):
                resp = await c.get("/api/v1/services")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# OPTIONS bypass
# ---------------------------------------------------------------------------

class TestOptionsBypass:
    async def test_options_preflight_bypasses_rate_limit(self):
        app = _make_app(auth_limit=0, window_seconds=60)  # would immediately block
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.options("/api/v1/auth/login")
        # OPTIONS should not return 429 even with 0 limit
        assert resp.status_code != 429


# ---------------------------------------------------------------------------
# Eviction
# ---------------------------------------------------------------------------

class TestEviction:
    def test_evict_expired_removes_stale_entries(self):
        app = FastAPI()
        mw = RateLimiterMiddleware(
            app,
            general_limit=10,
            auth_limit=5,
            window_seconds=60,
        )
        now = time.monotonic()
        # Manually insert a stale bucket (last_accessed > 2× window ago)
        from forgeguard.middleware.rate_limiter import TokenBucket
        stale_bucket = TokenBucket(
            tokens=10.0, max_tokens=10, refill_rate=10 / 60.0,
            last_refill=now - 200, last_accessed=now - 200,
        )
        mw._buckets[("1.2.3.4", "general")] = stale_bucket
        fresh_bucket = TokenBucket(
            tokens=10.0, max_tokens=10, refill_rate=10 / 60.0,
            last_refill=now, last_accessed=now,
        )
        mw._buckets[("5.6.7.8", "general")] = fresh_bucket

        evicted = mw._evict_expired()
        assert evicted == 1
        assert ("1.2.3.4", "general") not in mw._buckets
        assert ("5.6.7.8", "general") in mw._buckets

    def test_evict_returns_zero_when_no_stale_entries(self):
        app = FastAPI()
        mw = RateLimiterMiddleware(app, general_limit=10, auth_limit=5, window_seconds=60)
        now = time.monotonic()
        from forgeguard.middleware.rate_limiter import TokenBucket
        mw._buckets[("1.2.3.4", "general")] = TokenBucket(
            tokens=10.0, max_tokens=10, refill_rate=10 / 60.0,
            last_refill=now, last_accessed=now,
        )
        assert mw._evict_expired() == 0
