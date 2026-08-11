"""Platform health and observability endpoints for the Operator dashboard.

Routes:
    GET /api/v1/platform/health  — aggregated platform health summary (Operator/Admin only)

Authentication:
    A real JWT auth dependency will be wired in by the auth WO.  Until then
    this module uses a placeholder ``require_operator_role`` dependency that
    reads an ``X-User-Role`` header and raises ForbiddenError for unauthorised
    roles.  Replace with the real JWT dependency when WO-auth is complete.

Metrics source:
    Reads from in-memory prometheus_client Gauge/Counter objects defined in
    middleware/metrics.py — no database queries on this hot path so latency
    stays well under 1ms.
"""

from __future__ import annotations

import datetime
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from prometheus_client import REGISTRY

from forgeguard.core.exceptions import ForbiddenError
from forgeguard.middleware.metrics import (
    ASSESSMENT_QUEUE_DEPTH,
    AUDIT_LOG_WRITE_TOTAL,
    DB_POOL_CONNECTIONS_ACTIVE,
    DB_POOL_CONNECTIONS_SIZE,
    HTTP_REQUESTS_TOTAL,
    LLM_CIRCUIT_BREAKER_STATE,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/platform", tags=["platform", "observability"])

# Roles permitted to access the platform health endpoint.
_ALLOWED_ROLES: frozenset[str] = frozenset({"operator", "platform_admin"})

# Circuit breaker state integer → human-readable label.
_CIRCUIT_BREAKER_LABELS: dict[int, str] = {
    0: "closed",
    1: "open",
    2: "half-open",
}


# ---------------------------------------------------------------------------
# Auth placeholder
# ---------------------------------------------------------------------------

async def require_operator_role(request: Request) -> str:
    """Placeholder RBAC check — reads X-User-Role header.

    Replace with the real JWT auth dependency (``get_current_user``) when the
    auth WO is complete.  Raises :class:`ForbiddenError` for roles that are
    not permitted to view platform health data.
    """
    role = request.headers.get("X-User-Role", "").lower()
    if role not in _ALLOWED_ROLES:
        raise ForbiddenError(
            "Platform health data requires Operator or Platform Admin role.",
            required_permission="health.monitor",
            contact_role="operator",
        )
    return role


OperatorRoleDep = Annotated[str, Depends(require_operator_role)]


# ---------------------------------------------------------------------------
# Helpers — read in-memory prometheus_client metric values
# ---------------------------------------------------------------------------

def _read_counter_total(counter: Any, label_values: dict[str, str] | None = None) -> float:
    """Return the current cumulative value of a Counter (or labelled child)."""
    try:
        if label_values:
            return counter.labels(**label_values)._value.get()
        # For counters without labels, sum all child values via the registry.
        total = 0.0
        for metric in REGISTRY.collect():
            if metric.name == counter._name:
                for sample in metric.samples:
                    if sample.name.endswith("_total"):
                        total += sample.value
        return total
    except Exception:
        return 0.0


def _read_gauge_value(gauge: Any) -> float:
    """Return the current value of a label-less Gauge."""
    try:
        return gauge._value.get()
    except Exception:
        return 0.0


def _compute_api_success_rate() -> float:
    """Compute the percentage of requests with 2xx status across all-time counters.

    Returns a float 0.0–100.0 (or 100.0 when no requests have been recorded).
    """
    try:
        total = 0.0
        success = 0.0
        for metric in REGISTRY.collect():
            if metric.name != "http_requests_total":
                continue
            for sample in metric.samples:
                if not sample.name.endswith("_total"):
                    continue
                total += sample.value
                status = str(sample.labels.get("status_code", ""))
                if status.startswith("2"):
                    success += sample.value
        if total == 0:
            return 100.0
        return round((success / total) * 100, 2)
    except Exception:
        return 100.0


def _compute_audit_write_success_rate() -> float:
    """Return the audit log write success rate as a percentage (0–100)."""
    try:
        success = 0.0
        failure = 0.0
        for metric in REGISTRY.collect():
            if metric.name != "audit_log_write_total":
                continue
            for sample in metric.samples:
                if not sample.name.endswith("_total"):
                    continue
                status = sample.labels.get("status", "")
                if status == "success":
                    success += sample.value
                elif status == "failure":
                    failure += sample.value
        total = success + failure
        if total == 0:
            return 100.0
        return round((success / total) * 100, 2)
    except Exception:
        return 100.0


# ---------------------------------------------------------------------------
# Platform health endpoint
# ---------------------------------------------------------------------------

@router.get("/health", summary="Platform health summary (Operator)")
async def platform_health(
    _role: OperatorRoleDep,
) -> JSONResponse:
    """Return an aggregated platform health summary for the Operator dashboard.

    All values are derived from in-memory Prometheus counters and gauges
    collected by MetricsMiddleware — no database queries are performed so
    latency stays well under 1ms.

    Response fields:
        api_success_rate            — % of requests with 2xx status (all-time)
        assessment_completion_rate  — 100% if queue depth is 0, else lower
        audit_log_write_success_rate — % of audit writes that succeeded
        db_connection_pool_utilization — {active}/{size} fraction as a float
        llm_circuit_breaker_status  — "closed" | "open" | "half-open"
    """
    active_conns = _read_gauge_value(DB_POOL_CONNECTIONS_ACTIVE)
    pool_size = _read_gauge_value(DB_POOL_CONNECTIONS_SIZE)
    queue_depth = _read_gauge_value(ASSESSMENT_QUEUE_DEPTH)
    cb_state_int = int(_read_gauge_value(LLM_CIRCUIT_BREAKER_STATE))

    db_utilization = (
        round(active_conns / pool_size, 4) if pool_size > 0 else 0.0
    )
    assessment_completion_rate = 100.0 if queue_depth == 0 else round(
        max(0.0, (1.0 - queue_depth / max(queue_depth, 1)) * 100), 2
    )

    return JSONResponse(
        content={
            "status": "healthy",
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "api_success_rate": _compute_api_success_rate(),
            "assessment_completion_rate": assessment_completion_rate,
            "audit_log_write_success_rate": _compute_audit_write_success_rate(),
            "db_connection_pool_utilization": db_utilization,
            "llm_circuit_breaker_status": _CIRCUIT_BREAKER_LABELS.get(
                cb_state_int, "unknown"
            ),
        }
    )
