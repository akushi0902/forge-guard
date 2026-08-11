"""FindingRepository: async CRUD for the findings table."""

from __future__ import annotations

import uuid
from typing import Any

import asyncpg
import structlog

from forgeguard.data.repositories.base import BaseRepository

logger = structlog.get_logger(__name__)

_VALID_SEVERITIES = ("critical", "high", "medium", "low")

_ALLOWED_INSERT: frozenset[str] = frozenset({
    "id", "assessment_id", "service_id", "policy_rule_id",
    "severity", "dimension", "status", "title", "description",
    "evidence", "ai_explanation", "confidence_score",
})

_ALLOWED_UPDATE: frozenset[str] = frozenset({
    "severity", "status", "title", "description", "evidence",
    "ai_explanation", "confidence_score", "resolved_at",
})


class FindingRepository(BaseRepository):
    _table = "findings"

    async def get_by_id(
        self, id: str | uuid.UUID, *, include_deleted: bool = False
    ) -> dict[str, Any] | None:
        # findings has no deleted_at; include_deleted is accepted but unused
        q = "SELECT * FROM findings WHERE id = $1"
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
        q = "SELECT * FROM findings WHERE TRUE"
        if cursor:
            q += f" AND id > ${idx}"
            params.append(uuid.UUID(cursor))
            idx += 1
        q += f" ORDER BY id LIMIT ${idx}"
        params.append(limit)
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(q, *params)
        return self._rows(rows)

    async def create(self, data: dict[str, Any]) -> dict[str, Any]:
        query, values = self._safe_insert("findings", _ALLOWED_INSERT, data)
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
            f"UPDATE findings SET {set_clause}, updated_at = NOW() "
            f"WHERE id = ${len(values)} RETURNING *"
        )
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(q, *values)
        return self._row(row)

    async def soft_delete(self, id: str | uuid.UUID) -> bool:
        raise NotImplementedError(
            "Findings are not soft-deleted; use update_status('suppressed') instead"
        )

    async def find_by_service_and_severity(
        self, service_id: str | uuid.UUID, severity: str
    ) -> list[dict[str, Any]]:
        q = (
            "SELECT * FROM findings WHERE service_id = $1 AND severity = $2 "
            "ORDER BY created_at DESC"
        )
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(q, uuid.UUID(str(service_id)), severity)
        return self._rows(rows)

    async def find_by_assessment(
        self, assessment_id: str | uuid.UUID
    ) -> list[dict[str, Any]]:
        q = (
            "SELECT * FROM findings WHERE assessment_id = $1 "
            "ORDER BY severity, created_at DESC"
        )
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(q, uuid.UUID(str(assessment_id)))
        return self._rows(rows)

    async def count_by_severity(
        self, service_id: str | uuid.UUID
    ) -> dict[str, int]:
        q = (
            "SELECT severity, COUNT(*) AS count FROM findings "
            "WHERE service_id = $1 AND status != 'suppressed' GROUP BY severity"
        )
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(q, uuid.UUID(str(service_id)))
        counts: dict[str, int] = {sev: 0 for sev in _VALID_SEVERITIES}
        for row in rows:
            counts[row["severity"]] = int(row["count"])
        return counts

    async def update_status(
        self, id: str | uuid.UUID, status: str
    ) -> dict[str, Any] | None:
        q = (
            "UPDATE findings SET status = $1, updated_at = NOW() "
            "WHERE id = $2 RETURNING *"
        )
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(q, status, uuid.UUID(str(id)))
        return self._row(row)
