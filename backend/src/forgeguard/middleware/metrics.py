"""Prometheus metrics middleware — middleware stage #0 (innermost).

Records per-request counters and latency histograms using prometheus_client.
Metrics collection failures are non-fatal: errors are logged at WARNING
level and the request continues normally.

Metrics exposed:
    http_requests_total          — Counter (method, path, status_code)
    http_request_duration_seconds — Histogram (method, path)
    db_pool_connections_active   — Gauge (updated externally by the DB pool)
"""

from __future__ import annotations

import time
from typing import Callable

import structlog
from prometheus_client import Counter, Gauge, Histogram
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = structlog.get_logger(__name__)

HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total HTTP requests by method, path, and status code",
    ["method", "path", "status_code"],
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds by method and path",
    ["method", "path"],
)

DB_POOL_CONNECTIONS_ACTIVE = Gauge(
    "db_pool_connections_active",
    "Number of active database pool connections",
)


class MetricsMiddleware(BaseHTTPMiddleware):
    """Record request count and duration for every HTTP request."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start = time.perf_counter()
        method = request.method
        path = request.url.path
        status_code = "500"

        try:
            response = await call_next(request)
            status_code = str(response.status_code)
            return response
        except Exception:
            raise
        finally:
            try:
                duration = time.perf_counter() - start
                HTTP_REQUESTS_TOTAL.labels(
                    method=method, path=path, status_code=status_code
                ).inc()
                HTTP_REQUEST_DURATION_SECONDS.labels(
                    method=method, path=path
                ).observe(duration)
            except Exception as exc:
                logger.warning("metrics_collection_failed", error=str(exc))
