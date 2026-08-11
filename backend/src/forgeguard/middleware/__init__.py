"""ASGI middleware components for the ForgeGuard request pipeline.

Middleware is applied in the order it is registered on the FastAPI application.
The full middleware chain is defined in ``forgeguard.main.create_app``.

Planned middleware modules:
    request_id   — Assigns a UUID v4 correlation ID to every request
    logging      — Attaches request context to structlog bound variables
    rate_limiter — Token-bucket rate limiting per IP address
    cors         — CORS origin validation
    pii_filter   — Masks sensitive fields in request/response logs
    audit        — Pre-hook capturing before-state for mutation requests
"""
