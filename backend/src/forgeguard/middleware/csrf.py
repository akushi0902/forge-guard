"""CSRF token validation middleware — pipeline position 6.

Implements the synchronizer token pattern using a stateless HMAC-SHA256
approach: CSRF token = HMAC(jti, csrf_secret).  This ties each CSRF token to
a specific access token (via its unique JTI claim) without any server-side
storage.  When the access token is refreshed (new JTI), the old CSRF token
automatically becomes invalid.

Placement:
    Position 6 in the pipeline — AFTER AuthenticationMiddleware (pos 5) so
    that ``request.state.jti`` is already populated, and BEFORE
    SecurityHeadersMiddleware (pos 7) so that security headers are applied to
    all 403 responses.

Exempt from CSRF validation:
    - Safe methods: GET, HEAD, OPTIONS (no state mutation possible)
    - Public paths (same set as AuthenticationMiddleware)
    - Unauthenticated requests (auth middleware already returns 401)

Error responses:
    - Missing header   → 403  {"detail": "CSRF token required"}
    - Invalid/mismatch → 403  {"detail": "CSRF token invalid"}
"""

from __future__ import annotations

from typing import Any

import structlog
from starlette.requests import Request
from starlette.responses import JSONResponse

from forgeguard.core.security import validate_csrf_token
from forgeguard.middleware.authentication import PUBLIC_PATHS

logger = structlog.get_logger(__name__)

#: HTTP methods that do not mutate server state — exempt from CSRF checking.
_SAFE_METHODS: frozenset[str] = frozenset({"GET", "HEAD", "OPTIONS"})


def _forbidden(detail: str) -> JSONResponse:
    """Return a 403 JSONResponse for CSRF failures."""
    return JSONResponse(status_code=403, content={"detail": detail})


class CSRFMiddleware:
    """Pure ASGI CSRF validation middleware.

    Sits at pipeline position 6 — after AuthenticationMiddleware (needs
    ``request.state.jti``), before SecurityHeadersMiddleware.

    Constructor args:
        app:         The next ASGI application in the stack.
        csrf_secret: HMAC secret for CSRF token generation/validation.
                     Passed at registration time in
                     :func:`~forgeguard.main.create_app`.
    """

    def __init__(self, app: Any, *, csrf_secret: str = "") -> None:
        self._app = app
        self._csrf_secret = csrf_secret

    async def __call__(
        self, scope: dict[str, Any], receive: Any, send: Any
    ) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self._app(scope, receive, send)
            return

        request = Request(scope, receive)
        method: str = request.method
        path: str = request.url.path

        # Safe methods and public paths are exempt from CSRF validation.
        if method in _SAFE_METHODS or path in PUBLIC_PATHS:
            await self._app(scope, receive, send)
            return

        # If auth middleware didn't set jti (unauthenticated), let it pass
        # through — the auth middleware will have already returned 401 for
        # truly unauthenticated requests, so this branch handles only edge
        # cases such as public paths not listed in PUBLIC_PATHS.
        jti: str | None = getattr(request.state, "jti", None)
        if jti is None:
            await self._app(scope, receive, send)
            return

        # Validate the X-CSRF-Token request header.
        csrf_token: str | None = request.headers.get("x-csrf-token")

        if not csrf_token:
            logger.warning(
                "csrf.missing",
                path=path,
                method=method,
            )
            response = _forbidden("CSRF token required")
            await response(scope, receive, send)
            return

        if not validate_csrf_token(csrf_token, jti, self._csrf_secret):
            logger.warning(
                "csrf.invalid",
                path=path,
                method=method,
            )
            response = _forbidden("CSRF token invalid")
            await response(scope, receive, send)
            return

        await self._app(scope, receive, send)
