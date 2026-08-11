"""ServiceRepository: async CRUD for the services table."""

from __future__ import annotations

import uuid
from typing import Any

import asyncpg
import structlog

from forgeguard.data.repositories.base import BaseRepository

logger = structlog.get_logger(__name__)

# Note: the ORM attribute `service_metadata` maps to column `metadata` in PostgreSQL.
_ALLOWED_INSERT: frozenset[str] = frozenset({
    "id", "name", "description", "repository_url", "owner_team",
    "metadata", "forge_catalog_id", "is_demo",
})

_ALLOWED_UPDATE: frozenset[str] = frozenset({
    "name", "description", "repository_url", "owner_team",
    "metadata", "forge_catalog_id", "is_demo",
})


class ServiceRepository(BaseRepository):
    _table = "services"

    async def get_by_id(
        self, id: str | uuid.UUID, *, include_deleted: bool = False
    ) -> dict[str, Any] | None:
        q = "SELECT * FROM services WHERE id = $1"
        if not include_deleted:
            q += " AND deleted_at IS NULL"
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
        q = "SELECT * FROM services WHERE deleted_at IS NULL"
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
        query, values = self._safe_insert("services", _ALLOWED_INSERT, data)
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
            f"UPDATE services SET {set_clause}, updated_at = NOW() "
            f"WHERE id = ${len(values)} AND deleted_at IS NULL RETURNING *"
        )
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(q, *values)
        return self._row(row)

    async def soft_delete(self, id: str | uuid.UUID) -> bool:
        q = (
            "UPDATE services SET deleted_at = NOW() "
            "WHERE id = $1 AND deleted_at IS NULL"
        )
        async with self._pool.acquire() as conn:
            result = await conn.execute(q, uuid.UUID(str(id)))
        return result == "UPDATE 1"

    async def find_by_name(self, name: str) -> dict[str, Any] | None:
        q = "SELECT * FROM services WHERE name = $1 AND deleted_at IS NULL"
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(q, name)
        return self._row(row)

    async def list_with_latest_scores(
        self, *, cursor: str | None = None, limit: int = 20
    ) -> list[dict[str, Any]]:
        params: list[Any] = []
        idx = 1
        q = """
            SELECT s.*,
                   ls.overall_score AS latest_overall_score,
                   ls.score_type    AS latest_score_type,
                   ls.created_at    AS latest_score_created_at
            FROM services s
            LEFT JOIN LATERAL (
                SELECT overall_score, score_type, created_at
                FROM assessment_scores
                WHERE service_id = s.id
                ORDER BY created_at DESC
                LIMIT 1
            ) ls ON TRUE
            WHERE s.deleted_at IS NULL
        """
        if cursor:
            q += f" AND s.id > ${idx}"
            params.append(uuid.UUID(cursor))
            idx += 1
        q += f" ORDER BY s.id LIMIT ${idx}"
        params.append(limit)
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(q, *params)
        return self._rows(rows)

    async def find_demo_services(self) -> list[dict[str, Any]]:
        q = (
            "SELECT * FROM services WHERE is_demo = TRUE "
            "AND deleted_at IS NULL ORDER BY id"
        )
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(q)
        return self._rows(rows)
