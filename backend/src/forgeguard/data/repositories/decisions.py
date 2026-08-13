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

    async def update_workflow_status(
        self,
        id: str | uuid.UUID,
        *,
        workflow_id: str | None = None,
        routing_method: str | None = None,
        workflow_status: str | None = None,
        workflow_timeout_at: Any = None,
    ) -> dict[str, Any] | None:
        """Update workflow-tracking fields on a release_decisions row.

        Only the fields explicitly passed (non-None) are updated.
        This is the sole sanctioned mutation path for workflow state — the main
        ``update()`` method intentionally raises NotImplementedError.
        """
        sets: list[str] = []
        params: list[Any] = [uuid.UUID(str(id))]
        idx = 2

        if workflow_id is not None:
            sets.append(f"workflow_id = ${idx}")
            params.append(uuid.UUID(str(workflow_id)) if workflow_id else None)
            idx += 1
        if routing_method is not None:
            sets.append(f"routing_method = ${idx}")
            params.append(routing_method)
            idx += 1
        if workflow_status is not None:
            sets.append(f"workflow_status = ${idx}")
            params.append(workflow_status)
            idx += 1
        if workflow_timeout_at is not None:
            sets.append(f"workflow_timeout_at = ${idx}")
            params.append(workflow_timeout_at)
            idx += 1

        if not sets:
            return await self.get_by_id(id)

        q = (
            f"UPDATE release_decisions SET {', '.join(sets)} "
            f"WHERE id = $1 RETURNING *"
        )
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(q, *params)
        return self._row(row)

    async def list_active_workflows(self) -> list[dict[str, Any]]:
        """Return release_decisions rows with non-terminal workflow_status.

        Used by the 60-second polling job to determine which workflows to poll.
        """
        q = (
            "SELECT id, release_assessment_id, workflow_id, "
            "routing_method, workflow_status, workflow_timeout_at "
            "FROM release_decisions "
            "WHERE workflow_status IN ('pending', 'in_review') "
            "AND workflow_id IS NOT NULL "
            "ORDER BY created_at ASC"
        )
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(q)
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
