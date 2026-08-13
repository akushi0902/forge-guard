"""Services catalog sync REST API (WO-089).

Routes:
    GET /api/v1/services/{id}/catalog-sync — return Forge Catalog sync status

Authentication: JWT required (via AuthenticationMiddleware).
Authorization: SERVICE_VIEW permission required.
"""

from __future__ import annotations

import uuid
from typing import Any, Optional

import asyncpg
import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from forgeguard.api.dependencies.audit import get_audit_service
from forgeguard.api.dependencies.auth import CurrentUserDep
from forgeguard.core.dependencies import get_forge_catalog_adapter, get_service_repository
from forgeguard.core.permissions import Permissions, has_permission
from forgeguard.data.repositories.services import ServiceRepository
from forgeguard.services.audit import AuditService
from forgeguard.services.forge_catalog import ForgeCatalogAdapter

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/services", tags=["services"])


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class CatalogSyncStatusResponse(BaseModel):
    service_id: uuid.UUID
    forge_catalog_id: Optional[uuid.UUID]
    sync_status: str
    last_synced_at: Optional[str]
    last_error: Optional[str]

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get(
    "/{service_id}/catalog-sync",
    response_model=CatalogSyncStatusResponse,
    summary="Get Forge Catalog sync status for a service",
    description=(
        "Returns the current Forge Catalog synchronization state for the given service, "
        "including sync_status (pending/synced/failed/stale), forge_catalog_id, "
        "last_synced_at timestamp, and any last_error message."
    ),
)
async def get_catalog_sync_status(
    service_id: uuid.UUID,
    current_user: CurrentUserDep,
    service_repo: ServiceRepository = Depends(get_service_repository),
    catalog_adapter: ForgeCatalogAdapter = Depends(get_forge_catalog_adapter),
    audit: AuditService = Depends(get_audit_service),
) -> CatalogSyncStatusResponse:
    if not has_permission(current_user.role, Permissions.SERVICE_VIEW):
        raise HTTPException(status_code=403, detail="service.view permission required")

    service = await service_repo.get_by_id(service_id)
    if service is None:
        raise HTTPException(status_code=404, detail="Service not found")

    forge_catalog_id_raw = service.get("forge_catalog_id")
    forge_catalog_id = (
        uuid.UUID(str(forge_catalog_id_raw)) if forge_catalog_id_raw else None
    )

    sync_status = await catalog_adapter.get_sync_status(
        service_id=service_id,
        forge_catalog_id=forge_catalog_id,
        forge_sync_status=service.get("forge_sync_status", "pending"),
        last_synced_at=service.get("last_synced_at"),
        last_error=None,
    )

    logger.info(
        "catalog_sync_status_queried",
        service_id=str(service_id),
        sync_status=sync_status.get("sync_status"),
    )

    return CatalogSyncStatusResponse(
        service_id=uuid.UUID(str(sync_status["service_id"])),
        forge_catalog_id=(
            uuid.UUID(str(sync_status["forge_catalog_id"]))
            if sync_status.get("forge_catalog_id")
            else None
        ),
        sync_status=sync_status["sync_status"],
        last_synced_at=sync_status.get("last_synced_at"),
        last_error=sync_status.get("last_error"),
    )
