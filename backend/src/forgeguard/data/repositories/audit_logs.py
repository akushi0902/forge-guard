"""AuditLogRepository: append-only async access to the audit_logs table.

Public API: insert() and query() only.
The inherited update() and soft_delete() raise NotImplementedError to
enforce immutability at the application layer (in addition to DB-level
privilege restrictions set in the migration).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import asyncpg
import structlog

from forgeguard.data.repositories.base import BaseRepository

logger = structlog.get_logger(__name__)

_ALLOWED_INSERT: frozenset[str] = frozenset({
    "id", "actor_id", "actor_role", "action", "resource_type",
    "resource_id", "before_state", "after_state",
    "ip_address_masked", "correlation_id",
})


class AuditLogRepository(BaseRepository):
    _table = "audit_logs"

    async def get_by_id(
        self, id: str | uuid.UUID, *, include_deleted: bool = False
    ) -> dict[str, Any] | None:
        q = "SELECT * FROM audit_logs WHERE id = $1"
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(q, uuid.UUID(str(id)))
        return self._row(row)

    async def list(
        self,
        *,
        filters: dict[str, Any] | None = None,
        cursor: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        params: list[Any] = []
        idx = 1
        q = "SELECT * FROM audit_logs WHERE TRUE"
        if cursor:
            q += f" AND id > ${idx}"
            params.append(uuid.UUID(cursor))
            idx += 1
        q += f" ORDER BY created_at DESC LIMIT ${idx}"
        params.append(limit)
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(q, *params)
        return self._rows(rows)

    async def create(self, data: dict[str, Any]) -> dict[str, Any]:
        query, values = self._safe_insert("audit_logs", _ALLOWED_INSERT, data)
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, *values)
        return dict(row)  # type: ignore[arg-type]

    async def update(
        self, id: str | uuid.UUID, data: dict[str, Any]
    ) -> dict[str, Any] | None:
        raise NotImplementedError("audit_logs are immutable — no update allowed")

    async def soft_delete(self, id: str | uuid.UUID) -> bool:
        raise NotImplementedError("audit_logs are immutable — no delete allowed")

    # ------------------------------------------------------------------
    # Public append-only API
    # ------------------------------------------------------------------

    async def insert(self, data: dict[str, Any]) -> dict[str, Any]:
        """Insert a new immutable audit log entry and return the stored record."""
        return await self.create(data)

    async def query(
        self,
        *,
        actor_id: str | uuid.UUID | None = None,
        resource_type: str | None = None,
        action: str | None = None,
        after: datetime | None = None,
        before: datetime | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Query audit logs with optional filters.

        All filter values are positional parameters — no string interpolation.
        """
        params: list[Any] = []
        idx = 1
        q = "SELECT * FROM audit_logs WHERE TRUE"

        if actor_id is not None:
            q += f" AND actor_id = ${idx}"
            params.append(uuid.UUID(str(actor_id)))
            idx += 1
        if resource_type is not None:
            q += f" AND resource_type = ${idx}"
            params.append(resource_type)
            idx += 1
        if action is not None:
            q += f" AND action = ${idx}"
            params.append(action)
            idx += 1
        if after is not None:
            q += f" AND created_at >= ${idx}"
            params.append(after)
            idx += 1
        if before is not None:
            q += f" AND created_at < ${idx}"
            params.append(before)
            idx += 1
        if cursor is not None:
            q += f" AND id > ${idx}"
            params.append(uuid.UUID(cursor))
            idx += 1

        q += f" ORDER BY created_at DESC LIMIT ${idx}"
        params.append(limit)

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(q, *params)
        return self._rows(rows)
