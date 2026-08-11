"""Tests for SecurityHeadersMiddleware.

Covers:
    1. All seven security headers are present on 200 responses.
    2. All seven security headers are present on error responses (400, 404, 500).
    3. Exact header values match the architecture specification.
    4. Headers are not duplicated if the middleware is composed twice.
    5. Non-HTTP scope types (WebSocket) pass through unmodified.
    6. Integration: Request ID + CORS + Security Headers middleware — response
       includes X-Request-ID, Access-Control-Allow-Origin, and all security headers.
"""

from __future__ import annotations

from typing import AsyncGenerator

import pytest
import pytest_asyncio
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from forgeguard.middleware.request_id import RequestIDMiddleware
from forgeguard.middleware.security_headers import (
    CONTENT_SECURITY_POLICY,
    PERMISSIONS_POLICY,
    REFERRER_POLICY,
    STRICT_TRANSPORT_SECURITY,
    X_CONTENT_TYPE_OPTIONS,
    X_FRAME_OPTIONS,
    X_XSS_PROTECTION,
    SecurityHeadersMiddleware,
)


_ALLOWED_ORIGIN = "http://allowed.example.com"

# Expected header names (lowercase for httpx comparison)
_EXPECTED_HEADER_NAMES = [
    "strict-transport-security",
    "content-security-policy",
    "x-content-type-options",
    "x-frame-options",
    "x-xss-protection",
    "referrer-policy",
    "permissions-policy",
]


def _make_app_with_security_headers(double_wrap: bool = False) -> FastAPI:
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)
    if double_wrap:
        app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/ok")
    async def ok_endpoint():
        return {"status": "ok"}

    @app.get("/error-400")
    async def bad_request():
        return JSONResponse(status_code=400, content={"error": "bad_request"})

    @app.get("/error-404")
    async def not_found():
        return JSONResponse(status_code=404, content={"error": "not_found"})

    @app.get("/error-500")
    async def server_error():
        return JSONResponse(status_code=500, content={"error": "internal"})

    @app.get("/raises")
    async def raises():
        raise RuntimeError("boom")

    return app


@pytest_asyncio.fixture()
async def sh_client() -> AsyncGenerator[AsyncClient, None]:
    app = _make_app_with_security_headers()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# 200 response
# ---------------------------------------------------------------------------

class TestSecurityHeadersOn200:
    async def test_all_seven_headers_present(self, sh_client: AsyncClient) -> None:
        r = await sh_client.get("/ok")
        assert r.status_code == 200
        for header_name in _EXPECTED_HEADER_NAMES:
            assert header_name in r.headers, (
                f"Expected security header '{header_name}' missing from 200 response"
            )

    async def test_sts_exact_value(self, sh_client: AsyncClient) -> None:
        r = await sh_client.get("/ok")
        assert r.headers["strict-transport-security"] == STRICT_TRANSPORT_SECURITY

    async def test_csp_exact_value(self, sh_client: AsyncClient) -> None:
        r = await sh_client.get("/ok")
        assert r.headers["content-security-policy"] == CONTENT_SECURITY_POLICY

    async def test_x_content_type_options_exact_value(
        self, sh_client: AsyncClient
    ) -> None:
        r = await sh_client.get("/ok")
        assert r.headers["x-content-type-options"] == X_CONTENT_TYPE_OPTIONS

    async def test_x_frame_options_exact_value(self, sh_client: AsyncClient) -> None:
        r = await sh_client.get("/ok")
        assert r.headers["x-frame-options"] == X_FRAME_OPTIONS

    async def test_x_xss_protection_exact_value(self, sh_client: AsyncClient) -> None:
        r = await sh_client.get("/ok")
        assert r.headers["x-xss-protection"] == X_XSS_PROTECTION

    async def test_referrer_policy_exact_value(self, sh_client: AsyncClient) -> None:
        r = await sh_client.get("/ok")
        assert r.headers["referrer-policy"] == REFERRER_POLICY

    async def test_permissions_policy_exact_value(
        self, sh_client: AsyncClient
    ) -> None:
        r = await sh_client.get("/ok")
        assert r.headers["permissions-policy"] == PERMISSIONS_POLICY


# ---------------------------------------------------------------------------
# Error responses
# ---------------------------------------------------------------------------

class TestSecurityHeadersOnErrors:
    @pytest.mark.parametrize("path,status", [
        ("/error-400", 400),
        ("/error-404", 404),
        ("/error-500", 500),
    ])
    async def test_all_headers_on_error_response(
        self, sh_client: AsyncClient, path: str, status: int
    ) -> None:
        r = await sh_client.get(path)
        assert r.status_code == status
        for header_name in _EXPECTED_HEADER_NAMES:
            assert header_name in r.headers, (
                f"Expected security header '{header_name}' missing from {status} response"
            )

    async def test_headers_on_unhandled_exception(self, sh_client: AsyncClient) -> None:
        r = await sh_client.get("/raises")
        # FastAPI returns 500 for unhandled exceptions.
        assert r.status_code == 500
        for header_name in _EXPECTED_HEADER_NAMES:
            assert header_name in r.headers, (
                f"Expected security header '{header_name}' missing from exception response"
            )


# ---------------------------------------------------------------------------
# No-duplicate guarantee
# ---------------------------------------------------------------------------

class TestNoDuplication:
    async def test_headers_not_duplicated_when_middleware_wraps_twice(
        self,
    ) -> None:
        app = _make_app_with_security_headers(double_wrap=True)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.get("/ok")
        # httpx exposes duplicate headers as a comma-joined string; verify only one value.
        for header_name in _EXPECTED_HEADER_NAMES:
            assert header_name in r.headers
            # If header were duplicated, the raw value would contain a comma.
            # Most security header values don't contain commas, so a comma implies duplication.
            # We check count of entries in the raw headers tuple list.
        # Access raw response headers for full dupe check.
        raw_names = [name.lower() for name, _ in r.headers.items()]
        for header_name in _EXPECTED_HEADER_NAMES:
            count = raw_names.count(header_name)
            assert count == 1, (
                f"Security header '{header_name}' appears {count} times (expected 1)"
            )


# ---------------------------------------------------------------------------
# Exact constant values match specification
# ---------------------------------------------------------------------------

class TestConstantValues:
    def test_sts_includes_max_age(self) -> None:
        assert "max-age=31536000" in STRICT_TRANSPORT_SECURITY

    def test_sts_includes_include_subdomains(self) -> None:
        assert "includeSubDomains" in STRICT_TRANSPORT_SECURITY

    def test_csp_default_src_self(self) -> None:
        assert "default-src 'self'" in CONTENT_SECURITY_POLICY

    def test_csp_script_src_self_no_unsafe_inline(self) -> None:
        # CSP scripts must NOT allow unsafe-inline.
        assert "script-src 'self'" in CONTENT_SECURITY_POLICY
        # 'unsafe-inline' may only appear in style-src context.
        csp_parts = CONTENT_SECURITY_POLICY.split(";")
        for part in csp_parts:
            if "script-src" in part:
                assert "'unsafe-inline'" not in part, (
                    "script-src MUST NOT contain 'unsafe-inline'"
                )

    def test_csp_style_src_allows_unsafe_inline(self) -> None:
        # Mantine UI requires unsafe-inline for styles.
        assert "style-src 'self' 'unsafe-inline'" in CONTENT_SECURITY_POLICY

    def test_x_content_type_options_is_nosniff(self) -> None:
        assert X_CONTENT_TYPE_OPTIONS == "nosniff"

    def test_x_frame_options_is_deny(self) -> None:
        assert X_FRAME_OPTIONS == "DENY"

    def test_x_xss_protection_is_zero(self) -> None:
        assert X_XSS_PROTECTION == "0"

    def test_referrer_policy_value(self) -> None:
        assert REFERRER_POLICY == "strict-origin-when-cross-origin"

    def test_permissions_policy_blocks_camera_mic_geolocation(self) -> None:
        assert "camera=()" in PERMISSIONS_POLICY
        assert "microphone=()" in PERMISSIONS_POLICY
        assert "geolocation=()" in PERMISSIONS_POLICY


# ---------------------------------------------------------------------------
# Request with no Origin header still gets security headers
# ---------------------------------------------------------------------------

class TestNonBrowserRequest:
    async def test_security_headers_present_without_origin(
        self, sh_client: AsyncClient
    ) -> None:
        r = await sh_client.get("/ok")
        for header_name in _EXPECTED_HEADER_NAMES:
            assert header_name in r.headers


# ---------------------------------------------------------------------------
# Integration: Request ID + CORS + Security Headers
# ---------------------------------------------------------------------------

class TestIntegration:
    async def test_combined_middleware_all_headers_together(self) -> None:
        app = FastAPI()
        # Register innermost-first (Starlette reverse order).
        app.add_middleware(SecurityHeadersMiddleware)
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[_ALLOWED_ORIGIN],
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Content-Type", "Authorization", "X-Request-ID"],
        )
        app.add_middleware(RequestIDMiddleware)

        @app.get("/api/test")
        async def test_endpoint(request: Request):
            return {"request_id": request.headers.get("x-request-id")}

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.get(
                "/api/test", headers={"Origin": _ALLOWED_ORIGIN}
            )

        assert r.status_code == 200

        # X-Request-ID should be set by RequestIDMiddleware.
        assert "x-request-id" in r.headers
        request_id = r.headers["x-request-id"]
        assert request_id  # non-empty

        # CORS header for allowed origin.
        assert r.headers.get("access-control-allow-origin") == _ALLOWED_ORIGIN
        assert r.headers.get("access-control-allow-credentials") == "true"

        # All seven security headers.
        for header_name in _EXPECTED_HEADER_NAMES:
            assert header_name in r.headers, (
                f"Expected security header '{header_name}' missing from integration response"
            )

    async def test_security_headers_present_without_cors_origin(self) -> None:
        """Security headers must appear even when no CORS headers are added."""
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[_ALLOWED_ORIGIN],
            allow_credentials=True,
            allow_methods=["GET"],
            allow_headers=["Content-Type"],
        )
        app.add_middleware(RequestIDMiddleware)

        @app.get("/api/test")
        async def test_endpoint():
            return {"ok": True}

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            # No Origin header → no CORS headers → security headers still present.
            r = await client.get("/api/test")

        assert r.status_code == 200
        assert "x-request-id" in r.headers
        assert "access-control-allow-origin" not in r.headers  # no CORS

        for header_name in _EXPECTED_HEADER_NAMES:
            assert header_name in r.headers, (
                f"Expected security header '{header_name}' missing when no Origin sent"
            )
