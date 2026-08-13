"""Security headers middleware — middleware stage #5.

Injects the seven security headers mandated by the ForgeGuard security
architecture specification on every HTTP response, including error responses.

The middleware is implemented as a raw ASGI wrapper around the ``send``
callable so it intercepts ``http.response.start`` events at the ASGI level
rather than at the HTTP abstraction layer. This ensures headers are applied
to ALL responses — including those from inner middleware and route handlers —
without the overhead of parsing/re-serialising the full response body.

Security headers applied:
    Strict-Transport-Security : max-age=31536000; includeSubDomains
    Content-Security-Policy   : default-src 'self'; script-src 'self';
                                 style-src 'self' 'unsafe-inline'
    X-Content-Type-Options    : nosniff
    X-Frame-Options           : DENY
    X-XSS-Protection          : 0
    Referrer-Policy           : strict-origin-when-cross-origin
    Permissions-Policy        : camera=(), microphone=(), geolocation=()

Design notes:
    - ``'unsafe-inline'`` in style-src is required by Mantine UI (the React
      component library) which injects inline styles at runtime.
    - ``X-XSS-Protection: 0`` disables the legacy browser XSS filter, which
      can be exploited in some scenarios. Modern browsers rely on CSP instead.
    - Headers are not added if already present (prevents duplication if the
      middleware runs multiple times in a test harness).
    - Errors during header injection are logged at WARNING level; the original
      response is never blocked.
"""

from __future__ import annotations

import logging

from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Header constants
# ---------------------------------------------------------------------------

STRICT_TRANSPORT_SECURITY = "max-age=31536000; includeSubDomains"
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'"
)
X_CONTENT_TYPE_OPTIONS = "nosniff"
X_FRAME_OPTIONS = "DENY"
X_XSS_PROTECTION = "0"
REFERRER_POLICY = "strict-origin-when-cross-origin"
PERMISSIONS_POLICY = "camera=(), microphone=(), geolocation=()"

# Pre-encoded as bytes for zero-allocation injection into the ASGI header list.
_SECURITY_HEADERS: list[tuple[bytes, bytes]] = [
    (b"strict-transport-security", STRICT_TRANSPORT_SECURITY.encode()),
    (b"content-security-policy", CONTENT_SECURITY_POLICY.encode()),
    (b"x-content-type-options", X_CONTENT_TYPE_OPTIONS.encode()),
    (b"x-frame-options", X_FRAME_OPTIONS.encode()),
    (b"x-xss-protection", X_XSS_PROTECTION.encode()),
    (b"referrer-policy", REFERRER_POLICY.encode()),
    (b"permissions-policy", PERMISSIONS_POLICY.encode()),
]


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

class SecurityHeadersMiddleware:
    """Inject security headers into every HTTP response at the ASGI level.

    This is a raw ASGI middleware (not BaseHTTPMiddleware) to ensure headers
    reach the client even when an inner middleware short-circuits the request
    without calling a route handler.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_security_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                try:
                    existing_headers: list[tuple[bytes, bytes]] = list(
                        message.get("headers", [])
                    )
                    existing_names = {name.lower() for name, _ in existing_headers}
                    new_headers = [
                        (name, value)
                        for name, value in _SECURITY_HEADERS
                        if name not in existing_names
                    ]
                    message = {
                        **message,
                        "headers": existing_headers + new_headers,
                    }
                except Exception as exc:
                    logger.warning(
                        "security_headers_injection_failed: %s", exc, exc_info=True
                    )
            await send(message)

        await self.app(scope, receive, send_with_security_headers)
