"""AuditService: immutable audit event and mutation logging.

Every governance action, data mutation, and authentication event in ForgeGuard
produces an audit record through this service.  The service is the single
authoritative write path for the audit_logs table.

Design guarantees:
    - IP addresses are masked via :func:`~forgeguard.core.ip_masking.mask_ip_address`
      before persistence — raw PII never reaches the database.
    - JSONB columns are truncated at 1 MB to prevent unbounded storage; a
      truncation marker is appended so consumers know the record is incomplete.
    - Write failures are logged at ERROR level but callers receive the exception
      so they can decide whether to fail open (audit best-effort) or fail closed.
    - No UPDATE or DELETE paths exist — the service is append-only.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import structlog

from forgeguard.core.ip_masking import mask_ip_address
from forgeguard.data.repositories.audit_logs import AuditLogRepository

logger = structlog.get_logger(__name__)

#: Maximum size of a serialised JSONB value (1 MB).
_JSONB_MAX_BYTES: int = 1024 * 1024

#: Sentinel added to truncated JSONB to signal partial data.
_TRUNCATED_MARKER: dict[str, bool] = {"__truncated__": True}

#: System actor role used when no human actor is present.
SYSTEM_ACTOR_ROLE: str = "system"

#: System actor UUID placeholder for automated processes.
SYSTEM_ACTOR_ID: str | None = None


def _truncate_jsonb(value: dict[str, Any] | None) -> dict[str, Any] | None:
    """Truncate a JSONB dict if its JSON serialisation exceeds ``_JSONB_MAX_BYTES``.

    Returns None unchanged.  Truncated dicts include ``{"__truncated__": True}``
    in the returned value so consumers know the record is incomplete.
    """
    if value is None:
        return None
    try:
        encoded = json.dumps(value).encode("utf-8")
    except (TypeError, ValueError):
        return {"__unserializable__": True}

    if len(encoded) <= _JSONB_MAX_BYTES:
        return value

    return {**_TRUNCATED_MARKER, "size_bytes": len(encoded)}


class AuditService:
    """Append-only audit event writer.

    Args:
        audit_repo: Injected :class:`~forgeguard.data.repositories.audit_logs.AuditLogRepository`.
    """

    def __init__(self, audit_repo: AuditLogRepository) -> None:
        self._repo = audit_repo

    async def log_event(
        self,
        *,
        actor_id: uuid.UUID | str | None,
        actor_role: str,
        action: str,
        resource_type: str,
        resource_id: uuid.UUID | str | None = None,
        before_state: dict[str, Any] | None = None,
        after_state: dict[str, Any] | None = None,
        ip_address: str | None = None,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        """Persist a single immutable audit record.

        IP address masking is applied here — callers may pass a raw or already-
        masked IP; the service masks it again deterministically (idempotent).

        Args:
            actor_id:       UUID of the acting user, or None for system events.
            actor_role:     Role snapshot at event time.
            action:         Past-tense verb slug (e.g. ``"service.created"``).
            resource_type:  Domain entity type (e.g. ``"services"``).
            resource_id:    UUID of the affected entity; None for bulk ops.
            before_state:   Resource state before the mutation (None for creates).
            after_state:    Resource state after the mutation (None for deletes).
            ip_address:     Client IP address (raw or masked); will be masked.
            correlation_id: X-Request-ID from the originating request.

        Returns:
            The persisted audit record as a dict (from ``RETURNING *``).

        Raises:
            Exception: Propagates any database error after logging it at ERROR level.
        """
        masked_ip: str | None = mask_ip_address(ip_address) if ip_address else None

        actor_uuid: uuid.UUID | None = None
        if actor_id is not None:
            try:
                actor_uuid = uuid.UUID(str(actor_id))
            except ValueError:
                logger.warning("audit.log_event.invalid_actor_id", actor_id=str(actor_id))
                actor_uuid = None

        resource_uuid: uuid.UUID | None = None
        if resource_id is not None:
            try:
                resource_uuid = uuid.UUID(str(resource_id))
            except ValueError:
                pass

        record: dict[str, Any] = {
            "id": uuid.uuid4(),
            "actor_id": actor_uuid,
            "actor_role": actor_role or SYSTEM_ACTOR_ROLE,
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_uuid,
            "before_state": _truncate_jsonb(before_state),
            "after_state": _truncate_jsonb(after_state),
            "ip_address_masked": masked_ip,
            "correlation_id": str(correlation_id)[:36] if correlation_id else None,
        }

        try:
            result = await self._repo.insert(record)
            logger.debug(
                "audit.log_event.written",
                action=action,
                resource_type=resource_type,
                actor_role=actor_role,
            )
            return result
        except Exception as exc:
            logger.error(
                "audit.log_event.failed",
                action=action,
                resource_type=resource_type,
                actor_role=actor_role,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            raise

    async def log_mutation(
        self,
        *,
        actor_id: uuid.UUID | str | None,
        actor_role: str,
        action: str,
        resource_type: str,
        resource_id: uuid.UUID | str | None = None,
        before_state: dict[str, Any] | None = None,
        after_state: dict[str, Any] | None = None,
        ip_address: str | None = None,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        """Convenience wrapper around :meth:`log_event` for data mutations.

        Identical signature to :meth:`log_event` — exists so callers have a
        semantically distinct method for mutation events vs. authentication
        or governance decision events.
        """
        return await self.log_event(
            actor_id=actor_id,
            actor_role=actor_role,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            before_state=before_state,
            after_state=after_state,
            ip_address=ip_address,
            correlation_id=correlation_id,
        )
