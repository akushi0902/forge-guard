"""Admin endpoint for manually triggering the exception expiry scheduler.

Provides a manual trigger for Platform Admins to run the exception expiry
pass on-demand, useful for operational recovery and testing.

Routes:
    POST /api/v1/admin/run-expiration-check

Authentication: JWT cookie required. RBAC: Platform Admin (policy.manage).
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends, Request

from forgeguard.core.exceptions import ForbiddenError

logger = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/api/v1/admin",
    tags=["admin", "exception-expiry"],
)

_PLATFORM_ADMIN_ROLES = frozenset({"platform_admin"})


async def _require_platform_admin(request: Request) -> str:
    """Enforce Platform Admin role for manual expiry trigger.

    The RBAC middleware provides deny-by-default enforcement; this dependency
    provides an additional explicit guard so the handler communicates its
    requirements clearly.
    """
    user = getattr(request.state, "user", None)
    role = (user or {}).get("role", "") if isinstance(user, dict) else getattr(user, "role", "")
    if role not in _PLATFORM_ADMIN_ROLES:
        raise ForbiddenError(
            "Manual exception expiry trigger requires platform_admin role."
        )
    return role


@router.post(
    "/run-expiration-check",
    summary="Manual exception expiry trigger (Platform Admin)",
    response_model=dict,
    status_code=200,
)
async def run_expiration_check(
    request: Request,
    _role: str = Depends(_require_platform_admin),
) -> dict[str, Any]:
    """Manually trigger the exception expiry scheduler pass.

    Runs ``ExceptionExpiryScheduler.process_expired_exceptions()`` immediately
    and returns a summary of what was processed.  Safe to call multiple times
    (idempotent) — already-expired exceptions are skipped.
    """
    from forgeguard.data.database import get_pool  # noqa: PLC0415
    from forgeguard.data.repositories.audit_logs import AuditLogRepository  # noqa: PLC0415
    from forgeguard.services.audit import AuditService  # noqa: PLC0415
    from forgeguard.services.remediation.exception_expiry_scheduler import (  # noqa: PLC0415
        ExceptionExpiryScheduler,
    )

    pool = await get_pool()
    audit_service = AuditService(AuditLogRepository(pool))
    scheduler = ExceptionExpiryScheduler(pool=pool, audit_service=audit_service)

    logger.info(
        "admin.manual_expiry_triggered",
        actor=getattr(getattr(request.state, "user", None), "sub", "unknown"),
    )

    result = await scheduler.process_expired_exceptions()

    logger.info(
        "admin.manual_expiry_complete",
        processed=result["processed"],
        errors=result["errors"],
        affected_service_count=len(result["affected_service_ids"]),
    )

    return {
        "status": "ok",
        "processed": result["processed"],
        "errors": result["errors"],
        "skipped": result["skipped"],
        "affected_service_ids": result["affected_service_ids"],
    }
