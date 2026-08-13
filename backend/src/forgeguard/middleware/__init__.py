"""ASGI middleware components for the ForgeGuard request pipeline.

Middleware is applied in the order it is registered on the FastAPI application.
The full middleware chain is defined in ``forgeguard.main.create_app``.

Pipeline order (outermost → innermost, i.e. last registered → first registered):
    1. RequestIDMiddleware       — assigns UUID v4 correlation ID, clears stale context
    2. RequestLoggingMiddleware  — binds actor/resource/operation, logs lifecycle
    3. RateLimiterMiddleware     — token-bucket rate limiting per IP address
    4. CORSMiddleware            — CORS headers, pre-flight handling
    5. SecurityHeadersMiddleware — injects 7 security headers on all responses
    6. MetricsMiddleware         — records Prometheus counters and histograms
    7. (future) PiiFilterMiddleware — masks PII in request/response bodies
    8. (future) AuthMiddleware   — JWT validation, sets request.state.user
    9. AuditPreHookMiddleware    — captures before-state for mutation requests
"""
