"""DecisionAssignmentRepository: async CRUD for decision_assignments (WO-053)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import asyncpg
import structlog

from forgeguard.data.repositories.base import BaseRepository

logger = structlog.get_logger(__name__)

_ALLOWED_INSERT: frozenset[str] = frozenset({
    "id",
    "release_assessment_id",
    "assigned_role",
    "assigned_at",
    "status",
})

_ALLOWED_UPDATE: frozenset[str] = frozenset({
    "status",
    "completed_by",
    "completed_at",
    "updated_at",
})


class DecisionAssignmentRepository(BaseRepository):
    _table = "decision_assignments"

    async def get_by_id(
        self, id: str | uuid.UUID, *, include_deleted: bool = False
    ) -> dict[str, Any] | None:
        q = "SELECT * FROM decision_assignments WHERE id = $1"
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
        q = "SELECT * FROM decision_assignments WHERE TRUE"
        if filters:
            if role := filters.get("assigned_role"):
                q += f" AND assigned_role = ${idx}"
                params.append(role)
                idx += 1
            if status := filters.get("status"):
                q += f" AND status = ${idx}"
                params.append(status)
                idx += 1
        if cursor:
            q += f" AND created_at < ${idx}"
            params.append(cursor)
            idx += 1
        q += f" ORDER BY created_at DESC LIMIT ${idx}"
        params.append(limit)
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(q, *params)
        return self._rows(rows)

    async def create(self, data: dict[str, Any]) -> dict[str, Any]:
        query, values = self._safe_insert("decision_assignments", _ALLOWED_INSERT, data)
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
        q = f"UPDATE decision_assignments SET {set_clause} WHERE id = ${len(values)} RETURNING *"
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(q, *values)
        return self._row(row)

    async def soft_delete(self, id: str | uuid.UUID) -> bool:
        raise NotImplementedError("decision_assignments use status transitions, not soft-delete")

    # ------------------------------------------------------------------
    # Domain-specific queries
    # ------------------------------------------------------------------

    async def get_pending_by_role(
        self,
        role: str,
        *,
        cursor: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Return pending assignments for a given reviewer role, DESC by created_at.

        Supports cursor-based pagination using ISO 8601 created_at timestamps.
        """
        params: list[Any] = [role, "pending"]
        idx = 3
        q = """
            SELECT da.*, ra.service_id, ra.commit_sha, ra.pr_reference
            FROM decision_assignments da
            JOIN release_assessments ra ON ra.id = da.release_assessment_id
            WHERE da.assigned_role = $1
              AND da.status = $2
        """
        if cursor:
            q += f" AND da.created_at < ${idx}"
            params.append(cursor)
            idx += 1
        q += f" ORDER BY da.created_at DESC LIMIT ${idx}"
        params.append(limit)
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(q, *params)
        return self._rows(rows)

    async def get_pending_all(
        self,
        *,
        cursor: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Return all pending assignments across all roles (Platform Admin view)."""
        params: list[Any] = ["pending"]
        idx = 2
        q = """
            SELECT da.*, ra.service_id, ra.commit_sha, ra.pr_reference
            FROM decision_assignments da
            JOIN release_assessments ra ON ra.id = da.release_assessment_id
            WHERE da.status = $1
        """
        if cursor:
            q += f" AND da.created_at < ${idx}"
            params.append(cursor)
            idx += 1
        q += f" ORDER BY da.created_at DESC LIMIT ${idx}"
        params.append(limit)
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(q, *params)
        return self._rows(rows)

    async def get_by_assessment_id(
        self, release_assessment_id: str | uuid.UUID
    ) -> list[dict[str, Any]]:
        """Return all assignments for a given release assessment."""
        q = (
            "SELECT * FROM decision_assignments "
            "WHERE release_assessment_id = $1 ORDER BY created_at DESC"
        )
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(q, uuid.UUID(str(release_assessment_id)))
        return self._rows(rows)

    async def get_pending_by_assessment(
        self, release_assessment_id: str | uuid.UUID
    ) -> dict[str, Any] | None:
        """Return the pending assignment for a given assessment, if any."""
        q = (
            "SELECT * FROM decision_assignments "
            "WHERE release_assessment_id = $1 AND status = 'pending' "
            "LIMIT 1"
        )
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(q, uuid.UUID(str(release_assessment_id)))
        return self._row(row)

    async def mark_completed(
        self,
        release_assessment_id: str | uuid.UUID,
        completed_by: str | uuid.UUID | None,
    ) -> dict[str, Any] | None:
        """Transition the pending assignment for an assessment to completed.

        Idempotent: if no pending assignment exists, returns None without error.
        If completed_by is provided it is recorded as the reviewer who acted.
        """
        now = datetime.now(timezone.utc)
        q = """
            UPDATE decision_assignments
            SET status = 'completed',
                completed_by = $2,
                completed_at = $3,
                updated_at = $3
            WHERE release_assessment_id = $1
              AND status = 'pending'
            RETURNING *
        """
        completed_by_uuid = (
            uuid.UUID(str(completed_by)) if completed_by else None
        )
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                q, uuid.UUID(str(release_assessment_id)), completed_by_uuid, now
            )
        return self._row(row)

    async def mark_expired_batch(
        self,
        *,
        older_than_hours: int = 24,
    ) -> list[dict[str, Any]]:
        """Mark all pending assignments older than *older_than_hours* as expired.

        Returns the updated rows so callers can log them.
        """
        q = """
            UPDATE decision_assignments
            SET status = 'expired',
                updated_at = now()
            WHERE status = 'pending'
              AND assigned_at < now() - ($1 * INTERVAL '1 hour')
            RETURNING *
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(q, older_than_hours)
        return self._rows(rows)
