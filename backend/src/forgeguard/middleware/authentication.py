"""JWT authentication middleware — pipeline position 5.

Pure ASGI implementation (avoids BaseHTTPMiddleware overhead) that:
  - Skips public paths and OPTIONS preflight requests in O(1) set lookup.
  - Extracts the ``access_token`` httpOnly cookie.
  - Validates JWT signature and expiry via :func:`~forgeguard.core.security.decode_access_token`.
  - Attaches ``user_id`` and ``user_role`` to ``request.state`` for downstream handlers.
  - Binds ``user_id`` to the structlog context for all log entries in the request.
  - Returns 401 JSONResponse for missing, expired, or tampered tokens without
    leaking the signing key or internal token structure.

Error responses:
  - Missing cookie        → 401  {"detail": "Authentication required"}
  - Expired token         → 401  {"detail": "Token has expired"}
  - Tampered/invalid JWT  → 401  {"detail": "Invalid authentication token"}

All 401 responses carry a ``WWW-Authenticate: Bearer`` header per RFC 6750.
"""

from __future__ import annotations

from typing import Any

import structlog
from starlette.requests import Request
from starlette.responses import JSONResponse

from forgeguard.core.exceptions import UnauthorizedError
from forgeguard.core.security import decode_access_token

logger = structlog.get_logger(__name__)

#: Paths that bypass JWT authentication entirely (O(1) lookup).
PUBLIC_PATHS: frozenset[str] = frozenset({
    # Auth endpoints that issue or refresh tokens.
    "/api/v1/auth/login",
    "/api/v1/auth/register",
    "/api/v1/auth/refresh",
    "/api/v1/auth/logout",
    # Health / readiness / metrics probes.
    "/health",
    "/ready",
    "/metrics",
    "/api/v1/health",
    "/api/v1/ready",
    # OpenAPI docs.
    "/api/v1/docs",
    "/api/v1/redoc",
    "/api/v1/openapi.json",
    # Root liveness stub.
    "/",
    # GitHub webhook receiver — authenticated via HMAC-SHA256, not JWT.
    "/api/v1/webhooks/github",
})


def _unauthorized(detail: str) -> JSONResponse:
    """Return a 401 JSONResponse with WWW-Authenticate header."""
    return JSONResponse(
        status_code=401,
        content={"detail": detail},
        headers={"WWW-Authenticate": "Bearer"},
    )


class AuthenticationMiddleware:
    """Pure ASGI JWT authentication middleware.

    Sits at pipeline position 5 — after CORSMiddleware, before SecurityHeadersMiddleware.

    Constructor args:
        app:        The next ASGI application in the stack.
        jwt_secret: HMAC signing secret (``Settings.jwt_secret_key``).
                    Passed at registration time in :func:`~forgeguard.main.create_app`.
    """

    def __init__(self, app: Any, *, jwt_secret: str = "") -> None:
        self._app = app
        self._jwt_secret = jwt_secret

    async def __call__(
        self, scope: dict[str, Any], receive: Any, send: Any
    ) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self._app(scope, receive, send)
            return

        request = Request(scope, receive)
        path: str = request.url.path
        method: str = request.method

        # Public endpoints and CORS preflight bypass authentication.
        if path in PUBLIC_PATHS or method == "OPTIONS":
            await self._app(scope, receive, send)
            return

        # Require the access_token httpOnly cookie.
        access_token: str | None = request.cookies.get("access_token")
        if not access_token:
            response = _unauthorized("Authentication required")
            await response(scope, receive, send)
            return

        # Validate signature, expiry, and required claims.
        try:
            payload = decode_access_token(access_token, self._jwt_secret)
        except UnauthorizedError as exc:
            detail = (
                "Token has expired"
                if "expired" in str(exc).lower()
                else "Invalid authentication token"
            )
            logger.info(
                "auth.middleware.rejected",
                path=path,
                reason=detail,
            )
            response = _unauthorized(detail)
            await response(scope, receive, send)
            return

        # Attach authenticated identity to request.state for downstream use.
        request.state.user_id = payload["sub"]
        request.state.user_role = payload["role"]
        request.state.jti = payload["jti"]  # used by CSRFMiddleware at pos 6

        # Bind user_id to structlog context for the remainder of this request.
        structlog.contextvars.bind_contextvars(user_id=payload["sub"])

        await self._app(scope, receive, send)
