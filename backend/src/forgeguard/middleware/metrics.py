"""Prometheus metrics middleware — middleware stage #0 (innermost).

Records per-request counters and latency histograms using prometheus_client.
Metrics collection failures are non-fatal: errors are logged at WARNING
level and the request continues normally.

Metrics exposed:
    http_requests_total            — Counter  (method, endpoint, status_code)
    http_request_duration_seconds  — Histogram (method, endpoint)
                                     buckets: [0.005, 0.01, 0.025, 0.05, 0.1,
                                               0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
    http_requests_in_progress      — Gauge   (method, endpoint)
    db_pool_connections_active     — Gauge   (updated externally by the DB pool)
    db_pool_connections_size       — Gauge   (total pool size)
    assessment_queue_depth         — Gauge   (pending assessments, app-layer update)
    llm_circuit_breaker_state      — Gauge   (0=closed, 1=open, 2=half-open)
    audit_log_write_total          — Counter (status: success|failure)

Excluded from collection (no self-referential inflation):
    /metrics, /health, /ready

Path normalization:
    UUID segments and integer-only segments in the path are replaced with
    ``{id}`` to control Prometheus label cardinality.  For example:
        /api/v1/services/3fa85f64-5717-4562-b3fc-2c963f66afa6  →
        /api/v1/services/{id}
"""

from __future__ import annotations

import re
import time
from typing import Callable

import structlog
from prometheus_client import Counter, Gauge, Histogram
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Paths excluded from metrics collection
# ---------------------------------------------------------------------------

_EXCLUDED_PATHS: frozenset[str] = frozenset({"/metrics", "/health", "/ready"})

# ---------------------------------------------------------------------------
# Path normalization patterns
# ---------------------------------------------------------------------------

_UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE,
)
_INT_SEGMENT_RE = re.compile(r"(?<=/)\d+(?=/|$)")


def normalize_path(path: str) -> str:
    """Replace variable path segments with ``{id}`` placeholders.

    Prevents high-cardinality label explosion when paths contain UUIDs or
    integer record IDs.

    Examples::

        normalize_path("/api/v1/services/3fa85f64-.../assessments")
            → "/api/v1/services/{id}/assessments"
        normalize_path("/api/v1/findings/42")
            → "/api/v1/findings/{id}"
        normalize_path("/health")
            → "/health"
    """
    path = _UUID_RE.sub("{id}", path)
    path = _INT_SEGMENT_RE.sub("{id}", path)
    return path


# ---------------------------------------------------------------------------
# Prometheus metric singletons
# ---------------------------------------------------------------------------

HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total HTTP requests by method, endpoint template, and status code",
    ["method", "endpoint", "status_code"],
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds by method and endpoint template",
    ["method", "endpoint"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

HTTP_REQUESTS_IN_PROGRESS = Gauge(
    "http_requests_in_progress",
    "Number of HTTP requests currently being processed",
    ["method", "endpoint"],
)

DB_POOL_CONNECTIONS_ACTIVE = Gauge(
    "db_pool_connections_active",
    "Number of active database pool connections",
)

DB_POOL_CONNECTIONS_SIZE = Gauge(
    "db_pool_connections_size",
    "Total size of the database connection pool",
)

ASSESSMENT_QUEUE_DEPTH = Gauge(
    "assessment_queue_depth",
    "Number of assessments currently pending in the queue",
)

LLM_CIRCUIT_BREAKER_STATE = Gauge(
    "llm_circuit_breaker_state",
    "LLM circuit breaker state: 0=closed (healthy), 1=open (tripped), 2=half-open",
)

AUDIT_LOG_WRITE_TOTAL = Counter(
    "audit_log_write_total",
    "Total audit log write operations by status",
    ["status"],
)


class MetricsMiddleware(BaseHTTPMiddleware):
    """Record request count, in-progress gauge, and duration for every HTTP request.

    Excluded paths (/metrics, /health, /ready) pass through without recording
    to avoid self-referential label inflation and health-check noise.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path

        # Skip metrics collection for excluded paths.
        if path in _EXCLUDED_PATHS:
            return await call_next(request)

        method = request.method
        endpoint = normalize_path(path)
        status_code = "500"

        HTTP_REQUESTS_IN_PROGRESS.labels(method=method, endpoint=endpoint).inc()
        start = time.perf_counter()

        try:
            response = await call_next(request)
            status_code = str(response.status_code)
            return response
        except Exception:
            raise
        finally:
            try:
                duration = time.perf_counter() - start
                HTTP_REQUESTS_IN_PROGRESS.labels(
                    method=method, endpoint=endpoint
                ).dec()
                HTTP_REQUESTS_TOTAL.labels(
                    method=method, endpoint=endpoint, status_code=status_code
                ).inc()
                HTTP_REQUEST_DURATION_SECONDS.labels(
                    method=method, endpoint=endpoint
                ).observe(duration)
            except Exception as exc:
                logger.warning("metrics_collection_failed", error=str(exc))
