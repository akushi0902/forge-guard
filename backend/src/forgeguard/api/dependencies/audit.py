"""FastAPI dependency providers for the AuditService.

Usage::

    from forgeguard.api.dependencies.audit import get_audit_service
    from forgeguard.services.audit import AuditService

    @router.post("/services")
    async def create_service(
        body: ServiceCreate,
        audit: AuditService = Depends(get_audit_service),
    ) -> ServiceResponse:
        result = await svc_service.create(body)
        await audit.log_mutation(
            actor_id=request.state.actor_id,
            actor_role=request.state.user_role,
            action="service.created",
            resource_type="services",
            resource_id=result["id"],
            after_state=result,
        )
        return result
"""

from __future__ import annotations

import asyncpg
from fastapi import Depends

from forgeguard.core.dependencies import get_pool


async def get_audit_service(pool: asyncpg.Pool = Depends(get_pool)):
    """Provide an :class:`~forgeguard.services.audit.AuditService` instance.

    Instantiates :class:`~forgeguard.data.repositories.audit_logs.AuditLogRepository`
    with the shared connection pool and wraps it in :class:`~forgeguard.services.audit.AuditService`.

    Use via FastAPI ``Depends()``::

        audit: AuditService = Depends(get_audit_service)
    """
    from forgeguard.data.repositories.audit_logs import AuditLogRepository  # noqa: PLC0415
    from forgeguard.services.audit import AuditService  # noqa: PLC0415

    return AuditService(AuditLogRepository(pool))
