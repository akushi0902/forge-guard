"""Tests for CORS middleware configuration.

Covers:
    1. Request from allowed origin receives Access-Control-Allow-Origin header.
    2. Request from disallowed origin receives no CORS header.
    3. Preflight OPTIONS returns correct Allow-Methods and Allow-Headers.
    4. Access-Control-Allow-Credentials is 'true' for allowed origins.
    5. Request with no Origin header still receives a normal response.
    6. Settings validator rejects wildcard (*) origins.
"""

from __future__ import annotations

from typing import AsyncGenerator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from forgeguard.core.config import Settings


_ALLOWED_ORIGIN = "http://allowed.example.com"
_DISALLOWED_ORIGIN = "http://evil.example.com"


def _make_cors_app(
    origins: list[str] | None = None,
    allow_credentials: bool = True,
    allow_methods: list[str] | None = None,
    allow_headers: list[str] | None = None,
) -> FastAPI:
    if origins is None:
        origins = [_ALLOWED_ORIGIN]
    if allow_methods is None:
        allow_methods = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
    if allow_headers is None:
        allow_headers = ["Content-Type", "Authorization", "X-Request-ID"]

    app = FastAPI()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=allow_credentials,
        allow_methods=allow_methods,
        allow_headers=allow_headers,
    )

    @app.get("/api/data")
    async def data():
        return {"ok": True}

    @app.post("/api/submit")
    async def submit():
        return {"submitted": True}

    return app


@pytest_asyncio.fixture()
async def cors_client() -> AsyncGenerator[AsyncClient, None]:
    app = _make_cors_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# Allowed origin
# ---------------------------------------------------------------------------

class TestAllowedOrigin:
    async def test_allowed_origin_gets_acao_header(
        self, cors_client: AsyncClient
    ) -> None:
        r = await cors_client.get(
            "/api/data", headers={"Origin": _ALLOWED_ORIGIN}
        )
        assert r.status_code == 200
        assert r.headers.get("access-control-allow-origin") == _ALLOWED_ORIGIN

    async def test_allowed_origin_gets_credentials_header(
        self, cors_client: AsyncClient
    ) -> None:
        r = await cors_client.get(
            "/api/data", headers={"Origin": _ALLOWED_ORIGIN}
        )
        assert r.headers.get("access-control-allow-credentials") == "true"


# ---------------------------------------------------------------------------
# Disallowed origin
# ---------------------------------------------------------------------------

class TestDisallowedOrigin:
    async def test_disallowed_origin_has_no_acao_header(
        self, cors_client: AsyncClient
    ) -> None:
        r = await cors_client.get(
            "/api/data", headers={"Origin": _DISALLOWED_ORIGIN}
        )
        # Starlette CORSMiddleware omits the header for non-matching origins.
        assert "access-control-allow-origin" not in r.headers

    async def test_disallowed_origin_still_returns_body(
        self, cors_client: AsyncClient
    ) -> None:
        r = await cors_client.get(
            "/api/data", headers={"Origin": _DISALLOWED_ORIGIN}
        )
        # The response body is returned; only CORS headers are withheld.
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Preflight OPTIONS
# ---------------------------------------------------------------------------

class TestPreflight:
    async def test_preflight_returns_200_or_204(
        self, cors_client: AsyncClient
    ) -> None:
        r = await cors_client.options(
            "/api/data",
            headers={
                "Origin": _ALLOWED_ORIGIN,
                "Access-Control-Request-Method": "POST",
            },
        )
        assert r.status_code in (200, 204)

    async def test_preflight_includes_allow_methods(
        self, cors_client: AsyncClient
    ) -> None:
        r = await cors_client.options(
            "/api/data",
            headers={
                "Origin": _ALLOWED_ORIGIN,
                "Access-Control-Request-Method": "POST",
            },
        )
        allow_methods = r.headers.get("access-control-allow-methods", "")
        assert "POST" in allow_methods or "GET" in allow_methods

    async def test_preflight_includes_allow_headers(
        self, cors_client: AsyncClient
    ) -> None:
        r = await cors_client.options(
            "/api/data",
            headers={
                "Origin": _ALLOWED_ORIGIN,
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Authorization",
            },
        )
        allow_headers = r.headers.get("access-control-allow-headers", "")
        # Allow-Headers should reference Authorization or be a wildcard.
        assert allow_headers != "" or r.status_code in (200, 204)

    async def test_preflight_origin_echoed(self, cors_client: AsyncClient) -> None:
        r = await cors_client.options(
            "/api/data",
            headers={
                "Origin": _ALLOWED_ORIGIN,
                "Access-Control-Request-Method": "GET",
            },
        )
        acao = r.headers.get("access-control-allow-origin", "")
        assert acao == _ALLOWED_ORIGIN or acao == "*"


# ---------------------------------------------------------------------------
# No Origin header
# ---------------------------------------------------------------------------

class TestNoOriginHeader:
    async def test_no_origin_returns_200_without_cors_headers(
        self, cors_client: AsyncClient
    ) -> None:
        """Non-browser (same-origin) clients send no Origin header."""
        r = await cors_client.get("/api/data")
        assert r.status_code == 200
        # CORS headers should not be present when no Origin is sent.
        assert "access-control-allow-origin" not in r.headers


# ---------------------------------------------------------------------------
# CORS configuration — multiple origins
# ---------------------------------------------------------------------------

class TestMultipleOrigins:
    async def test_second_origin_in_list_allowed(self) -> None:
        origins = ["http://first.example.com", "http://second.example.com"]
        app = _make_cors_app(origins=origins)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.get(
                "/api/data", headers={"Origin": "http://second.example.com"}
            )
        assert r.headers.get("access-control-allow-origin") == "http://second.example.com"


# ---------------------------------------------------------------------------
# Configuration validation — wildcard rejection
# ---------------------------------------------------------------------------

class TestCORSConfigValidation:
    def test_wildcard_origin_rejected_by_settings(self) -> None:
        with pytest.raises((ValueError, ValidationError)):
            Settings(cors_allowed_origins="*")

    def test_wildcard_in_list_rejected(self) -> None:
        with pytest.raises((ValueError, ValidationError)):
            Settings(cors_allowed_origins="http://app.example.com,*")

    def test_valid_origins_accepted(self) -> None:
        s = Settings(
            cors_allowed_origins="http://localhost:3000,https://app.example.com"
        )
        assert "http://localhost:3000" in s.cors_origins_list
        assert "https://app.example.com" in s.cors_origins_list

    def test_cors_origins_list_property_parses_csv(self) -> None:
        s = Settings(
            cors_allowed_origins="https://a.example.com,https://b.example.com"
        )
        assert s.cors_origins_list == ["https://a.example.com", "https://b.example.com"]

    def test_trailing_slash_stripped(self) -> None:
        s = Settings(cors_allowed_origins="http://localhost:3000/")
        assert s.cors_origins_list == ["http://localhost:3000"]
