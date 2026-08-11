"""ReleaseAssessmentRepository: async CRUD for the release_assessments table."""

from __future__ import annotations

import json
import uuid
from typing import Any, Optional

import asyncpg
import structlog

from forgeguard.data.repositories.base import BaseRepository

logger = structlog.get_logger(__name__)

_ALLOWED_INSERT: frozenset[str] = frozenset({
    "id",
    "service_id",
    "commit_sha",
    "pr_reference",
    "requested_by",
    "status",
    "change_analysis",
    "completed_at",
})

_ALLOWED_UPDATE: frozenset[str] = frozenset({
    "status",
    "change_analysis",
    "completed_at",
})


class ReleaseAssessmentRepository(BaseRepository):
    """Append-and-update repository for release_assessments.

    change_analysis is stored as JSONB and serialized automatically via
    asyncpg's json_codec when the value is a dict.
    """

    _table = "release_assessments"

    async def get_by_id(
        self, id: str | uuid.UUID, *, include_deleted: bool = False
    ) -> dict[str, Any] | None:
        q = "SELECT * FROM release_assessments WHERE id = $1"
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
        q = "SELECT * FROM release_assessments WHERE TRUE"
        f = filters or {}

        if "service_id" in f:
            q += f" AND service_id = ${idx}"
            params.append(uuid.UUID(str(f["service_id"])))
            idx += 1
        if "status" in f:
            q += f" AND status = ${idx}"
            params.append(f["status"])
            idx += 1
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
        # Serialize change_analysis dict to JSON string for asyncpg
        normalized = self._normalize_jsonb(data)
        query, values = self._safe_insert("release_assessments", _ALLOWED_INSERT, normalized)
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, *values)
        return dict(row)  # type: ignore[arg-type]

    async def update(
        self, id: str | uuid.UUID, data: dict[str, Any]
    ) -> dict[str, Any] | None:
        normalized = self._normalize_jsonb(data)
        set_clause, values = self._safe_update_clause(_ALLOWED_UPDATE, normalized)
        if not set_clause:
            return await self.get_by_id(id)
        values.append(uuid.UUID(str(id)))
        q = (
            f"UPDATE release_assessments SET {set_clause}, updated_at = NOW() "
            f"WHERE id = ${len(values)} RETURNING *"
        )
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(q, *values)
        return self._row(row)

    async def soft_delete(self, id: str | uuid.UUID) -> bool:
        raise NotImplementedError(
            "release_assessments are retained for audit purposes — soft delete is not supported"
        )

    async def get_by_service(
        self,
        service_id: str | uuid.UUID,
        *,
        limit: int = 10,
        status: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Return recent assessments for a service, newest first."""
        params: list[Any] = [uuid.UUID(str(service_id))]
        q = "SELECT * FROM release_assessments WHERE service_id = $1"
        if status:
            q += " AND status = $2"
            params.append(status)
            q += " ORDER BY created_at DESC LIMIT $3"
            params.append(limit)
        else:
            q += " ORDER BY created_at DESC LIMIT $2"
            params.append(limit)
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(q, *params)
        return self._rows(rows)

    async def save_change_analysis(
        self,
        id: str | uuid.UUID,
        change_analysis: dict[str, Any],
        *,
        status: str = "completed",
    ) -> dict[str, Any] | None:
        """Persist the JSONB change analysis result and mark the assessment completed."""
        return await self.update(
            id,
            {
                "change_analysis": json.dumps(change_analysis),
                "status": status,
                "completed_at": "NOW()",
            },
        )

    async def list_page(
        self,
        *,
        service_id: Optional[str | uuid.UUID] = None,
        status: Optional[str] = None,
        before_created_at: Optional[Any] = None,
        before_id: Optional[str | uuid.UUID] = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Return assessments ordered by created_at DESC with proper cursor pagination.

        When both before_created_at and before_id are provided the query uses a
        composite keyset predicate: rows whose (created_at, id) is strictly before
        the cursor position (i.e. older or same-timestamp-but-earlier-id).
        """
        params: list[Any] = []
        idx = 1
        q = "SELECT * FROM release_assessments WHERE TRUE"

        if service_id is not None:
            q += f" AND service_id = ${idx}"
            params.append(uuid.UUID(str(service_id)))
            idx += 1
        if status is not None:
            q += f" AND status = ${idx}"
            params.append(status)
            idx += 1
        if before_created_at is not None and before_id is not None:
            q += (
                f" AND (created_at < ${idx}"
                f" OR (created_at = ${idx} AND id < ${idx + 1}))"
            )
            params.append(before_created_at)
            params.append(uuid.UUID(str(before_id)))
            idx += 2

        q += f" ORDER BY created_at DESC, id DESC LIMIT ${idx}"
        params.append(limit)
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(q, *params)
        return self._rows(rows)

    @staticmethod
    def _normalize_jsonb(data: dict[str, Any]) -> dict[str, Any]:
        """Serialize dict values in change_analysis to JSON strings for asyncpg."""
        if "change_analysis" in data and isinstance(data["change_analysis"], dict):
            return {**data, "change_analysis": json.dumps(data["change_analysis"])}
        return data
