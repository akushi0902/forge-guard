"""DecisionRepository: append-only async access to release_decisions."""

from __future__ import annotations

import uuid
from typing import Any

import asyncpg
import structlog

from forgeguard.data.repositories.base import BaseRepository

logger = structlog.get_logger(__name__)

_ALLOWED_INSERT: frozenset[str] = frozenset({
    "id", "release_assessment_id", "health_score_at_decision",
    "risk_score_at_decision", "decision", "decided_by_role",
    "decided_by", "rationale", "comment", "was_escalated",
})


class DecisionRepository(BaseRepository):
    _table = "release_decisions"

    async def get_by_id(
        self, id: str | uuid.UUID, *, include_deleted: bool = False
    ) -> dict[str, Any] | None:
        q = "SELECT * FROM release_decisions WHERE id = $1"
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
        q = "SELECT * FROM release_decisions WHERE TRUE"
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
        query, values = self._safe_insert("release_decisions", _ALLOWED_INSERT, data)
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, *values)
        return dict(row)  # type: ignore[arg-type]

    async def update(
        self, id: str | uuid.UUID, data: dict[str, Any]
    ) -> dict[str, Any] | None:
        raise NotImplementedError(
            "release_decisions are immutable — no update allowed"
        )

    async def soft_delete(self, id: str | uuid.UUID) -> bool:
        raise NotImplementedError(
            "release_decisions are immutable — no delete allowed"
        )

    async def find_by_release_assessment(
        self, release_assessment_id: str | uuid.UUID
    ) -> list[dict[str, Any]]:
        q = (
            "SELECT * FROM release_decisions "
            "WHERE release_assessment_id = $1 ORDER BY created_at ASC"
        )
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(q, uuid.UUID(str(release_assessment_id)))
        return self._rows(rows)

    async def list_by_service(
        self,
        service_id: str | uuid.UUID,
        *,
        cursor: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        params: list[Any] = [uuid.UUID(str(service_id))]
        idx = 2
        q = """
            SELECT rd.*
            FROM release_decisions rd
            JOIN release_assessments ra ON ra.id = rd.release_assessment_id
            WHERE ra.service_id = $1
        """
        if cursor:
            q += f" AND rd.id > ${idx}"
            params.append(uuid.UUID(cursor))
            idx += 1
        q += f" ORDER BY rd.created_at DESC LIMIT ${idx}"
        params.append(limit)
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(q, *params)
        return self._rows(rows)
