"""ScoreRepository: async access to assessment_scores (append-only, no update)."""

from __future__ import annotations

import uuid
from typing import Any

import asyncpg
import structlog

from forgeguard.data.repositories.base import BaseRepository

logger = structlog.get_logger(__name__)

_ALLOWED_INSERT: frozenset[str] = frozenset({
    "id", "assessment_id", "service_id", "score_type",
    "overall_score", "dimension_scores", "contributing_factors",
})


class ScoreRepository(BaseRepository):
    _table = "assessment_scores"

    async def get_by_id(
        self, id: str | uuid.UUID, *, include_deleted: bool = False
    ) -> dict[str, Any] | None:
        q = "SELECT * FROM assessment_scores WHERE id = $1"
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
        q = "SELECT * FROM assessment_scores WHERE TRUE"
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
        query, values = self._safe_insert("assessment_scores", _ALLOWED_INSERT, data)
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, *values)
        return dict(row)  # type: ignore[arg-type]

    async def update(
        self, id: str | uuid.UUID, data: dict[str, Any]
    ) -> dict[str, Any] | None:
        raise NotImplementedError("assessment_scores are immutable — no update allowed")

    async def soft_delete(self, id: str | uuid.UUID) -> bool:
        raise NotImplementedError("assessment_scores are not soft-deleted")

    async def get_latest_score(
        self, service_id: str | uuid.UUID, score_type: str
    ) -> dict[str, Any] | None:
        q = (
            "SELECT * FROM assessment_scores "
            "WHERE service_id = $1 AND score_type = $2 "
            "ORDER BY created_at DESC LIMIT 1"
        )
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(q, uuid.UUID(str(service_id)), score_type)
        return self._row(row)

    async def get_score_trend(
        self,
        service_id: str | uuid.UUID,
        score_type: str,
        days: int = 30,
    ) -> list[dict[str, Any]]:
        q = (
            "SELECT * FROM assessment_scores "
            "WHERE service_id = $1 AND score_type = $2 "
            "AND created_at >= NOW() - ($3 * INTERVAL '1 day') "
            "ORDER BY created_at ASC"
        )
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(q, uuid.UUID(str(service_id)), score_type, days)
        return self._rows(rows)

    async def create_with_dimensions(
        self, data: dict[str, Any]
    ) -> dict[str, Any]:
        """Insert an AssessmentScore record including dimension_scores JSONB."""
        return await self.create(data)
