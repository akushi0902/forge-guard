"""Forge Catalog bidirectional service sync adapter (WO-089).

Provides:
    ForgeCatalogAdapter     — abstract base class for catalog sync.
    ForgeCatalogHttpAdapter — concrete HTTP implementation with retry + cache.
    ForgeCatalogSyncStatus  — sync status string constants.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Optional

import structlog

from forgeguard.services.forge_catalog_client import (
    ForgeCatalogClientError,
    ForgeCatalogHttpClient,
)

logger = structlog.get_logger(__name__)


class ForgeCatalogSyncStatus:
    PENDING = "pending"
    SYNCED = "synced"
    FAILED = "failed"
    STALE = "stale"


class ForgeCatalogAdapter(ABC):
    """Abstract interface for Forge Catalog integration.

    Concrete implementations: ForgeCatalogHttpAdapter (production),
    mock implementations for tests.
    """

    @abstractmethod
    async def register_entity(
        self,
        *,
        service_id: uuid.UUID,
        name: str,
        description: Optional[str],
        owner_team: Optional[str],
        metadata: dict[str, Any],
        actor_id: Optional[uuid.UUID | str] = None,
    ) -> dict[str, Any]:
        """Register a new service in the Forge Catalog via POST.

        Returns dict: {forge_catalog_id, sync_status, last_synced_at, last_error}.
        Must not raise — failures set sync_status=failed.
        """

    @abstractmethod
    async def update_entity(
        self,
        *,
        service_id: uuid.UUID,
        forge_catalog_id: uuid.UUID,
        name: str,
        description: Optional[str],
        owner_team: Optional[str],
        metadata: dict[str, Any],
        actor_id: Optional[uuid.UUID | str] = None,
    ) -> dict[str, Any]:
        """Update an existing Forge Catalog entity via PUT."""

    @abstractmethod
    async def sync_service(
        self,
        *,
        service_id: uuid.UUID,
        forge_catalog_id: Optional[uuid.UUID],
        name: str,
        description: Optional[str],
        owner_team: Optional[str],
        metadata: dict[str, Any],
        actor_id: Optional[uuid.UUID | str] = None,
    ) -> dict[str, Any]:
        """Register or update a service, choosing the correct HTTP verb."""

    @abstractmethod
    async def get_entity(
        self,
        *,
        service_id: uuid.UUID,
        forge_catalog_id: uuid.UUID,
    ) -> Optional[dict[str, Any]]:
        """Retrieve a catalog entity by its ID (cache-first)."""

    @abstractmethod
    async def get_sync_status(
        self,
        *,
        service_id: uuid.UUID,
        forge_catalog_id: Optional[uuid.UUID],
        forge_sync_status: str,
        last_synced_at: Optional[datetime],
        last_error: Optional[str] = None,
    ) -> dict[str, Any]:
        """Build the sync status response payload from stored service fields."""


class ForgeCatalogHttpAdapter(ForgeCatalogAdapter):
    """Forge Catalog HTTP adapter.

    Wraps ForgeCatalogHttpClient with:
    - Graceful degradation: sync failures set status=failed without blocking callers
    - 409 Conflict handling: falls back to PUT when POST conflicts
    - Audit logging for every sync operation
    - Structured logging with service_id, catalog_entity_id, sync_status, retry_attempt

    Args:
        client:        Configured ForgeCatalogHttpClient.
        audit_service: AuditService instance for immutable audit records; optional.
    """

    PROVIDER_NAME = "forge_catalog"

    def __init__(
        self,
        client: ForgeCatalogHttpClient,
        audit_service: Any = None,
    ) -> None:
        self._client = client
        self._audit = audit_service

    async def _log_audit(
        self,
        *,
        actor_id: Optional[uuid.UUID | str],
        action: str,
        service_id: uuid.UUID,
        before_state: Optional[dict[str, Any]] = None,
        after_state: Optional[dict[str, Any]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        if self._audit is None:
            return
        try:
            await self._audit.log_event(
                actor_id=actor_id,
                actor_role="system",
                action=action,
                resource_type="services",
                resource_id=service_id,
                before_state=before_state,
                after_state=after_state,
                metadata=metadata,
            )
        except Exception:
            logger.warning(
                "forge_catalog_audit_log_failed",
                action=action,
                service_id=str(service_id),
            )

    def _failure_result(
        self,
        exc: ForgeCatalogClientError,
        *,
        forge_catalog_id: Optional[str] = None,
    ) -> dict[str, Any]:
        cached = self._client.get_cached_state(
            forge_catalog_id or "__unknown__"
        ) if not forge_catalog_id else None
        return {
            "forge_catalog_id": forge_catalog_id
            or (cached.get("id") if cached else None),
            "sync_status": ForgeCatalogSyncStatus.FAILED,
            "last_synced_at": None,
            "last_error": f"HTTP {exc.status_code} at {exc.endpoint}",
        }

    async def register_entity(
        self,
        *,
        service_id: uuid.UUID,
        name: str,
        description: Optional[str],
        owner_team: Optional[str],
        metadata: dict[str, Any],
        actor_id: Optional[uuid.UUID | str] = None,
    ) -> dict[str, Any]:
        log = logger.bind(service_id=str(service_id), sync_status="started")
        log.info("catalog_sync_started", operation="register")
        await self._log_audit(
            actor_id=actor_id,
            action="catalog_sync_started",
            service_id=service_id,
            metadata={"operation": "register"},
        )

        try:
            result = await self._client.create_entity(
                name=name,
                description=description,
                entity_type="service",
                metadata=metadata,
                owner=owner_team,
            )
        except ForgeCatalogClientError as exc:
            log.warning(
                "catalog_sync_failed",
                endpoint=exc.endpoint,
                status_code=exc.status_code,
                retried=exc.retried,
            )
            await self._log_audit(
                actor_id=actor_id,
                action="catalog_sync_failed",
                service_id=service_id,
                after_state={
                    "sync_status": ForgeCatalogSyncStatus.FAILED,
                    "error": f"HTTP {exc.status_code}",
                },
            )
            cached = self._client.get_cached_state(service_id)
            return {
                "forge_catalog_id": cached.get("id") if cached else None,
                "sync_status": ForgeCatalogSyncStatus.FAILED,
                "last_synced_at": None,
                "last_error": f"HTTP {exc.status_code} at {exc.endpoint}",
            }

        if result.get("_conflict"):
            # 409 Conflict — entity already exists; switch to PUT
            log.info("catalog_conflict_switching_to_update", name=name)
            existing = await self._client.find_entity_by_name(name)
            if existing:
                catalog_id = existing.get("id")
                try:
                    update_result = await self._client.update_entity(
                        catalog_id,
                        name=name,
                        description=description,
                        metadata=metadata,
                        owner=owner_team,
                    )
                    self._client.cache_state(service_id, update_result)
                    now = datetime.now(timezone.utc)
                    log.info(
                        "catalog_sync_succeeded",
                        catalog_entity_id=str(catalog_id),
                        sync_status="synced",
                    )
                    await self._log_audit(
                        actor_id=actor_id,
                        action="catalog_sync_succeeded",
                        service_id=service_id,
                        after_state={
                            "sync_status": ForgeCatalogSyncStatus.SYNCED,
                            "forge_catalog_id": str(catalog_id),
                        },
                    )
                    return {
                        "forge_catalog_id": catalog_id,
                        "sync_status": ForgeCatalogSyncStatus.SYNCED,
                        "last_synced_at": now.isoformat(),
                        "last_error": None,
                    }
                except ForgeCatalogClientError as exc:
                    log.warning("catalog_sync_failed", endpoint=exc.endpoint, status_code=exc.status_code)
                    await self._log_audit(
                        actor_id=actor_id,
                        action="catalog_sync_failed",
                        service_id=service_id,
                        after_state={"sync_status": ForgeCatalogSyncStatus.FAILED},
                    )
                    return {
                        "forge_catalog_id": str(catalog_id) if catalog_id else None,
                        "sync_status": ForgeCatalogSyncStatus.FAILED,
                        "last_synced_at": None,
                        "last_error": f"HTTP {exc.status_code} at {exc.endpoint}",
                    }

        catalog_id = result.get("id")
        self._client.cache_state(service_id, result)
        now = datetime.now(timezone.utc)
        log.info(
            "catalog_sync_succeeded",
            catalog_entity_id=str(catalog_id),
            sync_status="synced",
        )
        await self._log_audit(
            actor_id=actor_id,
            action="catalog_sync_succeeded",
            service_id=service_id,
            after_state={
                "sync_status": ForgeCatalogSyncStatus.SYNCED,
                "forge_catalog_id": str(catalog_id),
            },
        )
        return {
            "forge_catalog_id": catalog_id,
            "sync_status": ForgeCatalogSyncStatus.SYNCED,
            "last_synced_at": now.isoformat(),
            "last_error": None,
        }

    async def update_entity(
        self,
        *,
        service_id: uuid.UUID,
        forge_catalog_id: uuid.UUID,
        name: str,
        description: Optional[str],
        owner_team: Optional[str],
        metadata: dict[str, Any],
        actor_id: Optional[uuid.UUID | str] = None,
    ) -> dict[str, Any]:
        log = logger.bind(
            service_id=str(service_id),
            catalog_entity_id=str(forge_catalog_id),
        )
        log.info("catalog_sync_started", operation="update")
        await self._log_audit(
            actor_id=actor_id,
            action="catalog_sync_started",
            service_id=service_id,
            metadata={"operation": "update", "catalog_id": str(forge_catalog_id)},
        )

        try:
            result = await self._client.update_entity(
                forge_catalog_id,
                name=name,
                description=description,
                metadata=metadata,
                owner=owner_team,
            )
        except ForgeCatalogClientError as exc:
            log.warning(
                "catalog_sync_failed",
                endpoint=exc.endpoint,
                status_code=exc.status_code,
                retried=exc.retried,
            )
            await self._log_audit(
                actor_id=actor_id,
                action="catalog_sync_failed",
                service_id=service_id,
                after_state={"sync_status": ForgeCatalogSyncStatus.FAILED},
            )
            return {
                "forge_catalog_id": str(forge_catalog_id),
                "sync_status": ForgeCatalogSyncStatus.FAILED,
                "last_synced_at": None,
                "last_error": f"HTTP {exc.status_code} at {exc.endpoint}",
            }

        self._client.cache_state(service_id, result)
        now = datetime.now(timezone.utc)
        log.info("catalog_sync_succeeded", sync_status="synced")
        await self._log_audit(
            actor_id=actor_id,
            action="catalog_sync_succeeded",
            service_id=service_id,
            after_state={"sync_status": ForgeCatalogSyncStatus.SYNCED},
        )
        return {
            "forge_catalog_id": str(forge_catalog_id),
            "sync_status": ForgeCatalogSyncStatus.SYNCED,
            "last_synced_at": now.isoformat(),
            "last_error": None,
        }

    async def sync_service(
        self,
        *,
        service_id: uuid.UUID,
        forge_catalog_id: Optional[uuid.UUID],
        name: str,
        description: Optional[str],
        owner_team: Optional[str],
        metadata: dict[str, Any],
        actor_id: Optional[uuid.UUID | str] = None,
    ) -> dict[str, Any]:
        if forge_catalog_id is None:
            return await self.register_entity(
                service_id=service_id,
                name=name,
                description=description,
                owner_team=owner_team,
                metadata=metadata,
                actor_id=actor_id,
            )
        return await self.update_entity(
            service_id=service_id,
            forge_catalog_id=forge_catalog_id,
            name=name,
            description=description,
            owner_team=owner_team,
            metadata=metadata,
            actor_id=actor_id,
        )

    async def get_entity(
        self,
        *,
        service_id: uuid.UUID,
        forge_catalog_id: uuid.UUID,
    ) -> Optional[dict[str, Any]]:
        cached = self._client.get_cached_state(service_id)
        if cached:
            return cached
        try:
            result = await self._client.get_entity_by_id(forge_catalog_id)
            self._client.cache_state(service_id, result)
            return result
        except ForgeCatalogClientError:
            return None

    async def get_sync_status(
        self,
        *,
        service_id: uuid.UUID,
        forge_catalog_id: Optional[uuid.UUID],
        forge_sync_status: str,
        last_synced_at: Optional[datetime],
        last_error: Optional[str] = None,
    ) -> dict[str, Any]:
        return {
            "service_id": str(service_id),
            "forge_catalog_id": str(forge_catalog_id) if forge_catalog_id else None,
            "sync_status": forge_sync_status,
            "last_synced_at": last_synced_at.isoformat() if last_synced_at else None,
            "last_error": last_error,
        }
