"""Tests for RequestIDMiddleware.

Test structure:
    TestUUID4Parsing         — _parse_uuid4 helper handles edge cases correctly
    TestNoIncomingHeader     — generates a fresh UUID v4 when no header present
    TestValidIncomingHeader  — reuses a valid UUID v4 from X-Request-ID
    TestInvalidIncomingHeader — generates new UUID for malformed / non-v4 headers
    TestRequestStateAccess   — correlation_id and request_id both set on state
    TestConcurrentRequests   — unique IDs assigned under concurrent load
    TestIntegration          — full round-trip: header propagation end-to-end
"""

from __future__ import annotations

import asyncio
import re
import uuid

import pytest
import pytest_asyncio
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from forgeguard.middleware.request_id import RequestIDMiddleware, _parse_uuid4

# ── UUID v4 regex ────────────────────────────────────────────────────────────
_UUID4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _is_uuid4(value: str) -> bool:
    return bool(_UUID4_RE.match(value))


# ── Test app factory ─────────────────────────────────────────────────────────

def _make_app() -> FastAPI:
    """Minimal FastAPI app with RequestIDMiddleware and an echo endpoint."""
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)

    @app.get("/echo")
    async def echo_correlation_id(request: Request):
        return {
            "correlation_id": request.state.correlation_id,
            "request_id": request.state.request_id,
        }

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


@pytest_asyncio.fixture()
async def client() -> AsyncClient:
    app = _make_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as c:
        yield c


# ---------------------------------------------------------------------------
# _parse_uuid4 helper — unit tests
# ---------------------------------------------------------------------------

class TestUUID4Parsing:
    def test_valid_uuid4_lowercase(self):
        v = str(uuid.uuid4())
        assert _parse_uuid4(v) == v

    def test_valid_uuid4_uppercase_accepted(self):
        v = str(uuid.uuid4()).upper()
        result = _parse_uuid4(v)
        assert result is not None
        assert result == v.lower()

    def test_valid_uuid4_with_whitespace_stripped(self):
        v = str(uuid.uuid4())
        result = _parse_uuid4(f"  {v}  ")
        assert result == v

    def test_uuid_version_1_rejected(self):
        v = str(uuid.uuid1())
        assert _parse_uuid4(v) is None

    def test_uuid_version_3_rejected(self):
        v = str(uuid.uuid3(uuid.NAMESPACE_DNS, "example.com"))
        assert _parse_uuid4(v) is None

    def test_uuid_version_5_rejected(self):
        v = str(uuid.uuid5(uuid.NAMESPACE_DNS, "example.com"))
        assert _parse_uuid4(v) is None

    def test_empty_string_rejected(self):
        assert _parse_uuid4("") is None

    def test_plain_string_rejected(self):
        assert _parse_uuid4("not-a-uuid") is None

    def test_truncated_uuid_rejected(self):
        assert _parse_uuid4("12345678-1234-4") is None

    def test_none_like_value_rejected(self):
        assert _parse_uuid4("null") is None


# ---------------------------------------------------------------------------
# No incoming header — generates a fresh UUID v4
# ---------------------------------------------------------------------------

class TestNoIncomingHeader:
    async def test_response_has_x_request_id(self, client: AsyncClient) -> None:
        response = await client.get("/health")
        assert "x-request-id" in response.headers

    async def test_generated_id_is_uuid4(self, client: AsyncClient) -> None:
        response = await client.get("/health")
        rid = response.headers["x-request-id"]
        assert _is_uuid4(rid), f"Expected UUID v4, got: {rid!r}"

    async def test_successive_requests_get_different_ids(
        self, client: AsyncClient
    ) -> None:
        r1 = await client.get("/health")
        r2 = await client.get("/health")
        assert (
            r1.headers["x-request-id"] != r2.headers["x-request-id"]
        ), "Two requests without X-Request-ID must not share an ID"


# ---------------------------------------------------------------------------
# Valid incoming header — reused unchanged
# ---------------------------------------------------------------------------

class TestValidIncomingHeader:
    async def test_valid_uuid4_echoed_back(self, client: AsyncClient) -> None:
        incoming = str(uuid.uuid4())
        response = await client.get("/health", headers={"X-Request-ID": incoming})
        assert response.headers["x-request-id"] == incoming

    async def test_valid_uuid4_uppercase_normalised(
        self, client: AsyncClient
    ) -> None:
        incoming = str(uuid.uuid4()).upper()
        response = await client.get("/health", headers={"X-Request-ID": incoming})
        # Should be accepted and normalised to lowercase.
        assert response.headers["x-request-id"] == incoming.lower()

    async def test_valid_id_set_on_request_state(
        self, client: AsyncClient
    ) -> None:
        incoming = str(uuid.uuid4())
        response = await client.get("/echo", headers={"X-Request-ID": incoming})
        body = response.json()
        assert body["correlation_id"] == incoming
        assert body["request_id"] == incoming


# ---------------------------------------------------------------------------
# Invalid incoming header — generates a new UUID v4
# ---------------------------------------------------------------------------

class TestInvalidIncomingHeader:
    @pytest.mark.parametrize(
        "bad_value",
        [
            "not-a-uuid",
            "12345678-1234-1234-1234-123456789012",  # UUID v1-style (wrong version bit)
            "",
            "  ",
            "00000000-0000-0000-0000-000000000000",  # nil UUID (version 0)
            "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx",  # template, not real UUID
        ],
    )
    async def test_invalid_header_generates_new_uuid(
        self, client: AsyncClient, bad_value: str
    ) -> None:
        response = await client.get(
            "/health", headers={"X-Request-ID": bad_value}
        )
        rid = response.headers["x-request-id"]
        assert _is_uuid4(rid), f"Expected a fresh UUID v4, got: {rid!r}"
        # Must NOT echo the bad value back.
        assert rid != bad_value

    async def test_uuid_v1_not_accepted(self, client: AsyncClient) -> None:
        uuid1_val = str(uuid.uuid1())
        response = await client.get(
            "/health", headers={"X-Request-ID": uuid1_val}
        )
        rid = response.headers["x-request-id"]
        # uuid1 looks like a UUID but is not v4; middleware must generate new.
        assert _is_uuid4(rid)
        assert rid != uuid1_val


# ---------------------------------------------------------------------------
# request.state — both attributes are set
# ---------------------------------------------------------------------------

class TestRequestStateAccess:
    async def test_correlation_id_in_state(self, client: AsyncClient) -> None:
        incoming = str(uuid.uuid4())
        response = await client.get("/echo", headers={"X-Request-ID": incoming})
        assert response.json()["correlation_id"] == incoming

    async def test_request_id_backward_compat_alias(
        self, client: AsyncClient
    ) -> None:
        """request.state.request_id is kept for backward compat with error handlers."""
        incoming = str(uuid.uuid4())
        response = await client.get("/echo", headers={"X-Request-ID": incoming})
        assert response.json()["request_id"] == incoming

    async def test_both_state_attrs_equal(self, client: AsyncClient) -> None:
        response = await client.get("/echo")
        body = response.json()
        assert body["correlation_id"] == body["request_id"]
        assert _is_uuid4(body["correlation_id"])


# ---------------------------------------------------------------------------
# Concurrent requests — unique IDs
# ---------------------------------------------------------------------------

class TestConcurrentRequests:
    async def test_concurrent_requests_get_unique_ids(
        self, client: AsyncClient
    ) -> None:
        responses = await asyncio.gather(
            *[client.get("/health") for _ in range(20)]
        )
        ids = [r.headers["x-request-id"] for r in responses]
        assert len(set(ids)) == 20, "Concurrent requests must each receive a unique ID"

    async def test_all_concurrent_ids_are_uuid4(
        self, client: AsyncClient
    ) -> None:
        responses = await asyncio.gather(
            *[client.get("/health") for _ in range(10)]
        )
        for r in responses:
            assert _is_uuid4(r.headers["x-request-id"])


# ---------------------------------------------------------------------------
# Integration — full round-trip header propagation
# ---------------------------------------------------------------------------

class TestIntegration:
    async def test_request_without_header_gets_uuid4_in_response(
        self, client: AsyncClient
    ) -> None:
        response = await client.get("/health")
        assert response.status_code == 200
        rid = response.headers.get("x-request-id")
        assert rid is not None
        assert _is_uuid4(rid)

    async def test_request_with_valid_header_echoed_in_response(
        self, client: AsyncClient
    ) -> None:
        my_id = str(uuid.uuid4())
        response = await client.get("/health", headers={"X-Request-ID": my_id})
        assert response.status_code == 200
        assert response.headers["x-request-id"] == my_id

    async def test_correlation_id_accessible_in_route_handler(
        self, client: AsyncClient
    ) -> None:
        my_id = str(uuid.uuid4())
        response = await client.get("/echo", headers={"X-Request-ID": my_id})
        assert response.status_code == 200
        body = response.json()
        assert body["correlation_id"] == my_id

    async def test_x_request_id_present_on_404_response(
        self, client: AsyncClient
    ) -> None:
        """X-Request-ID must appear even on 404 (non-existent route)."""
        response = await client.get("/nonexistent-route")
        assert "x-request-id" in response.headers
        assert _is_uuid4(response.headers["x-request-id"])

    async def test_empty_string_header_generates_new_id(
        self, client: AsyncClient
    ) -> None:
        response = await client.get("/health", headers={"X-Request-ID": ""})
        rid = response.headers["x-request-id"]
        assert _is_uuid4(rid)
        assert rid != ""
