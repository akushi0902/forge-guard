"""AssessmentRepository: async CRUD for the assessments table (WO-042)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import asyncpg
import structlog

from forgeguard.data.repositories.base import BaseRepository

logger = structlog.get_logger(__name__)

_ALLOWED_INSERT: frozenset[str] = frozenset({
    "id", "service_id", "assessment_type", "trigger_type",
    "triggered_by", "status", "collected_data",
    "started_at", "completed_at",
})

_ALLOWED_UPDATE: frozenset[str] = frozenset({
    "status", "collected_data", "started_at", "completed_at", "error_details",
})


class AssessmentRepository(BaseRepository):
    _table = "assessments"

    async def get_by_id(
        self, id: str | uuid.UUID, *, include_deleted: bool = False
    ) -> dict[str, Any] | None:
        q = "SELECT * FROM assessments WHERE id = $1"
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
        q = "SELECT * FROM assessments WHERE TRUE"
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
        query, values = self._safe_insert("assessments", _ALLOWED_INSERT, data)
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, *values)
        return dict(row)  # type: ignore[arg-type]

    async def update(
        self, id: str | uuid.UUID, data: dict[str, Any]
    ) -> dict[str, Any] | None:
        set_clause, values = self._safe_update_clause(_ALLOWED_UPDATE, data)
        if not set_clause:
            return await self.get_by_id(id)
        values.append(uuid.UUID(str(id)))
        q = (
            f"UPDATE assessments SET {set_clause}, updated_at = NOW() "
            f"WHERE id = ${len(values)} RETURNING *"
        )
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(q, *values)
        return self._row(row)

    async def soft_delete(self, id: str | uuid.UUID) -> bool:
        raise NotImplementedError("assessments are not soft-deleted")

    async def check_in_progress(
        self, service_id: str | uuid.UUID
    ) -> dict[str, Any] | None:
        """Return the in-progress assessment for a service, or None.

        Used to enforce the constraint that only one assessment can run at a time
        per service — callers return 409 Conflict if this is non-None.
        """
        q = (
            "SELECT * FROM assessments "
            "WHERE service_id = $1 AND status = 'in_progress' "
            "ORDER BY created_at DESC LIMIT 1"
        )
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(q, uuid.UUID(str(service_id)))
        return self._row(row)

    async def update_status(
        self,
        id: str | uuid.UUID,
        status: str,
        *,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        error_details: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Convenience wrapper that sets status and optional timestamp fields."""
        data: dict[str, Any] = {"status": status}
        if started_at is not None:
            data["started_at"] = started_at
        if completed_at is not None:
            data["completed_at"] = completed_at
        if error_details is not None:
            data["error_details"] = error_details
        return await self.update(id, data)
