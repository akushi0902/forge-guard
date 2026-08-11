"""Tests for the token bucket rate-limiting middleware.

Test structure:
    TestTokenBucket     — unit tests for the TokenBucket data class
    TestRateLimiterWithinLimit  — requests within budget succeed
    TestRateLimiterExceedsLimit — exceeding budget returns HTTP 429
    TestRateLimiterTiers        — auth paths use the stricter limit
    TestRateLimiterClientIP     — IP extraction and per-IP isolation
    TestRateLimiterOptions      — OPTIONS requests bypass rate limiting
    TestRateLimiterEviction     — expired buckets are cleaned up
    TestRateLimiterIntegration  — 429 body includes correlation ID from RequestIDMiddleware
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from forgeguard.middleware.rate_limiter import RateLimiterMiddleware, TokenBucket
from forgeguard.middleware.request_id import RequestIDMiddleware


# ---------------------------------------------------------------------------
# Shared test-app factory
# ---------------------------------------------------------------------------

def _make_app(
    general_limit: int = 5,
    auth_limit: int = 2,
    window_seconds: int = 60,
    auth_paths: list[str] | None = None,
    include_request_id: bool = False,
) -> FastAPI:
    """Return a minimal FastAPI app with rate-limiter middleware."""
    if auth_paths is None:
        auth_paths = ["/auth/"]

    app = FastAPI()

    # Middleware registration is innermost-first (Starlette reverse order).
    app.add_middleware(
        RateLimiterMiddleware,
        general_limit=general_limit,
        auth_limit=auth_limit,
        window_seconds=window_seconds,
        auth_paths=auth_paths,
    )
    if include_request_id:
        app.add_middleware(RequestIDMiddleware)

    @app.get("/api/data")
    async def general_endpoint():
        return {"ok": True}

    @app.get("/auth/login")
    async def auth_endpoint():
        return {"ok": True}

    @app.options("/api/data")
    async def options_endpoint():
        return {}

    return app


@pytest_asyncio.fixture()
async def client() -> AsyncGenerator[AsyncClient, None]:
    app = _make_app(general_limit=5, auth_limit=2)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture()
async def client_with_request_id() -> AsyncGenerator[AsyncClient, None]:
    app = _make_app(general_limit=5, auth_limit=2, include_request_id=True)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# TokenBucket unit tests
# ---------------------------------------------------------------------------

class TestTokenBucket:
    def test_new_bucket_starts_full(self) -> None:
        bucket = TokenBucket(
            tokens=5.0, max_tokens=5, refill_rate=5 / 60, last_refill=time.monotonic()
        )
        allowed, retry = bucket.consume()
        assert allowed is True
        assert retry == 0
        assert bucket.tokens == pytest.approx(4.0, abs=0.01)

    def test_consume_fails_when_empty(self) -> None:
        bucket = TokenBucket(
            tokens=0.0, max_tokens=5, refill_rate=5 / 60, last_refill=time.monotonic()
        )
        allowed, retry = bucket.consume()
        assert allowed is False
        assert retry >= 1

    def test_retry_after_is_positive_integer(self) -> None:
        bucket = TokenBucket(
            tokens=0.0, max_tokens=10, refill_rate=10 / 60, last_refill=time.monotonic()
        )
        _, retry = bucket.consume()
        assert isinstance(retry, int)
        assert retry >= 1

    def test_refill_restores_tokens_after_elapsed_time(self) -> None:
        refill_rate = 1.0  # 1 token per second
        bucket = TokenBucket(
            tokens=0.0,
            max_tokens=10,
            refill_rate=refill_rate,
            last_refill=time.monotonic() - 5,  # 5 seconds ago
        )
        bucket.refill()
        # Should have gained ~5 tokens
        assert bucket.tokens == pytest.approx(5.0, abs=0.1)

    def test_refill_does_not_exceed_max_tokens(self) -> None:
        bucket = TokenBucket(
            tokens=0.0,
            max_tokens=3,
            refill_rate=100.0,   # very fast refill
            last_refill=time.monotonic() - 100,
        )
        bucket.refill()
        assert bucket.tokens == pytest.approx(3.0, abs=0.01)

    def test_successive_consumes_decrement_tokens(self) -> None:
        bucket = TokenBucket(
            tokens=3.0, max_tokens=3, refill_rate=3 / 60, last_refill=time.monotonic()
        )
        for _ in range(3):
            allowed, _ = bucket.consume()
            assert allowed is True
        allowed, retry = bucket.consume()
        assert allowed is False
        assert retry >= 1


# ---------------------------------------------------------------------------
# Requests within the limit succeed
# ---------------------------------------------------------------------------

class TestRateLimiterWithinLimit:
    async def test_requests_within_general_limit_return_200(
        self, client: AsyncClient
    ) -> None:
        for _ in range(5):
            r = await client.get("/api/data")
            assert r.status_code == 200

    async def test_requests_within_auth_limit_return_200(
        self, client: AsyncClient
    ) -> None:
        for _ in range(2):
            r = await client.get("/auth/login")
            assert r.status_code == 200


# ---------------------------------------------------------------------------
# Exceeding the limit returns HTTP 429
# ---------------------------------------------------------------------------

class TestRateLimiterExceedsLimit:
    async def test_exceeding_general_limit_returns_429(
        self, client: AsyncClient
    ) -> None:
        for _ in range(5):
            await client.get("/api/data")
        r = await client.get("/api/data")
        assert r.status_code == 429

    async def test_exceeding_auth_limit_returns_429(
        self, client: AsyncClient
    ) -> None:
        for _ in range(2):
            await client.get("/auth/login")
        r = await client.get("/auth/login")
        assert r.status_code == 429

    async def test_429_has_retry_after_header(self, client: AsyncClient) -> None:
        for _ in range(5):
            await client.get("/api/data")
        r = await client.get("/api/data")
        assert r.status_code == 429
        assert "retry-after" in r.headers
        retry_after = int(r.headers["retry-after"])
        assert retry_after >= 1

    async def test_429_body_has_required_fields(self, client: AsyncClient) -> None:
        for _ in range(5):
            await client.get("/api/data")
        r = await client.get("/api/data")
        assert r.status_code == 429
        body = r.json()
        assert body["error"] == "rate_limit_exceeded"
        assert "message" in body
        assert "retry_after" in body
        assert body["retry_after"] >= 1

    async def test_429_body_retry_after_matches_header(
        self, client: AsyncClient
    ) -> None:
        for _ in range(5):
            await client.get("/api/data")
        r = await client.get("/api/data")
        body = r.json()
        header_val = int(r.headers["retry-after"])
        assert body["retry_after"] == header_val

    async def test_429_message_includes_retry_seconds(
        self, client: AsyncClient
    ) -> None:
        for _ in range(5):
            await client.get("/api/data")
        r = await client.get("/api/data")
        body = r.json()
        assert str(body["retry_after"]) in body["message"]


# ---------------------------------------------------------------------------
# Auth vs general tier differentiation
# ---------------------------------------------------------------------------

class TestRateLimiterTiers:
    async def test_auth_path_exhausts_before_general(
        self, client: AsyncClient
    ) -> None:
        # Auth limit is 2; general limit is 5.
        # After 2 auth requests the auth path is blocked but general still works.
        for _ in range(2):
            await client.get("/auth/login")
        auth_r = await client.get("/auth/login")
        assert auth_r.status_code == 429

        general_r = await client.get("/api/data")
        assert general_r.status_code == 200

    async def test_general_exhausted_does_not_affect_auth_bucket(
        self, client: AsyncClient
    ) -> None:
        # Exhaust general bucket.
        for _ in range(5):
            await client.get("/api/data")
        general_r = await client.get("/api/data")
        assert general_r.status_code == 429

        # Auth bucket is independent — still has capacity.
        auth_r = await client.get("/auth/login")
        assert auth_r.status_code == 200


# ---------------------------------------------------------------------------
# Client IP extraction and per-IP independence
# ---------------------------------------------------------------------------

class TestRateLimiterClientIP:
    async def test_different_ips_have_independent_buckets(
        self, client: AsyncClient
    ) -> None:
        # Exhaust IP 1.
        for _ in range(5):
            await client.get("/api/data", headers={"X-Forwarded-For": "10.0.0.1"})
        ip1_r = await client.get("/api/data", headers={"X-Forwarded-For": "10.0.0.1"})
        assert ip1_r.status_code == 429

        # IP 2 must still be within budget.
        ip2_r = await client.get("/api/data", headers={"X-Forwarded-For": "10.0.0.2"})
        assert ip2_r.status_code == 200

    async def test_x_forwarded_for_leftmost_ip_used(
        self, client: AsyncClient
    ) -> None:
        # Only exhaust via the leftmost IP in a proxy chain.
        for _ in range(5):
            await client.get(
                "/api/data",
                headers={"X-Forwarded-For": "192.168.1.1, 10.0.0.1, 172.16.0.1"},
            )
        r = await client.get(
            "/api/data",
            headers={"X-Forwarded-For": "192.168.1.1, 10.0.0.2"},
        )
        assert r.status_code == 429  # leftmost IP (192.168.1.1) is exhausted


# ---------------------------------------------------------------------------
# OPTIONS requests bypass rate limiting
# ---------------------------------------------------------------------------

class TestRateLimiterOptions:
    async def test_options_requests_not_counted(self, client: AsyncClient) -> None:
        # Send many OPTIONS requests — none should count toward the limit.
        for _ in range(20):
            r = await client.options("/api/data")
            assert r.status_code in (200, 204, 405)

        # Regular GET should still succeed (bucket untouched by OPTIONS).
        r = await client.get("/api/data")
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Eviction of expired buckets
# ---------------------------------------------------------------------------

class TestRateLimiterEviction:
    def test_evict_expired_removes_stale_buckets(self) -> None:
        from forgeguard.middleware.rate_limiter import RateLimiterMiddleware

        app_inner = FastAPI()
        mw = RateLimiterMiddleware(
            app_inner,
            general_limit=10,
            auth_limit=5,
            window_seconds=60,
        )

        # Create 500 buckets with old last_accessed timestamps.
        stale_time = time.monotonic() - (60 * 3)  # 3× the window
        for i in range(500):
            key = (f"10.0.{i // 256}.{i % 256}", "general")
            mw._buckets[key] = TokenBucket(
                tokens=10.0,
                max_tokens=10,
                refill_rate=10 / 60,
                last_refill=stale_time,
                last_accessed=stale_time,
            )

        assert len(mw._buckets) == 500
        evicted = mw._evict_expired()
        assert evicted == 500
        assert len(mw._buckets) == 0

    def test_recent_buckets_not_evicted(self) -> None:
        from forgeguard.middleware.rate_limiter import RateLimiterMiddleware

        app_inner = FastAPI()
        mw = RateLimiterMiddleware(
            app_inner,
            general_limit=10,
            auth_limit=5,
            window_seconds=60,
        )

        now = time.monotonic()
        for i in range(10):
            key = (f"10.0.0.{i}", "general")
            mw._buckets[key] = TokenBucket(
                tokens=5.0,
                max_tokens=10,
                refill_rate=10 / 60,
                last_refill=now,
                last_accessed=now,
            )

        evicted = mw._evict_expired()
        assert evicted == 0
        assert len(mw._buckets) == 10


# ---------------------------------------------------------------------------
# Integration test: 429 body includes correlation ID from RequestIDMiddleware
# ---------------------------------------------------------------------------

class TestRateLimiterIntegration:
    async def test_429_body_includes_correlation_id(
        self, client_with_request_id: AsyncClient
    ) -> None:
        """When RequestIDMiddleware runs first, the 429 body must contain its ID."""
        for _ in range(5):
            await client_with_request_id.get("/api/data")
        r = await client_with_request_id.get("/api/data")
        assert r.status_code == 429
        body = r.json()
        # reference_id must be a valid UUID (set by RequestIDMiddleware)
        ref_id = body.get("reference_id")
        assert ref_id is not None, "reference_id missing from 429 body"
        try:
            uuid.UUID(ref_id)
        except ValueError:
            pytest.fail(f"reference_id {ref_id!r} is not a valid UUID")

    async def test_429_response_has_request_id_header(
        self, client_with_request_id: AsyncClient
    ) -> None:
        for _ in range(5):
            await client_with_request_id.get("/api/data")
        r = await client_with_request_id.get("/api/data")
        assert r.status_code == 429
        assert "x-request-id" in r.headers

    async def test_reference_id_matches_x_request_id_header(
        self, client_with_request_id: AsyncClient
    ) -> None:
        for _ in range(5):
            await client_with_request_id.get("/api/data")
        r = await client_with_request_id.get("/api/data")
        assert r.status_code == 429
        body = r.json()
        assert body["reference_id"] == r.headers.get("x-request-id")
