"""ExceptionRepository: async CRUD for the exceptions table (WO-062, WO-064)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import asyncpg
import structlog

from forgeguard.data.repositories.base import BaseRepository

logger = structlog.get_logger(__name__)

_ALLOWED_INSERT: frozenset[str] = frozenset({
    "id",
    "finding_id",
    "requested_by",
    "justification",
    "status",
    "approver_role",
    "expires_at",
})

_ALLOWED_UPDATE: frozenset[str] = frozenset({
    "status",
    "decided_by",
    "decision_comment",
    "decided_at",
    "approver_role",
})


class ExceptionRepository(BaseRepository):
    _table = "exceptions"

    async def get_by_id(
        self, id: str | uuid.UUID, *, include_deleted: bool = False
    ) -> dict[str, Any] | None:
        q = "SELECT * FROM exceptions WHERE id = $1"
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
        q = "SELECT * FROM exceptions WHERE TRUE"
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
        query, values = self._safe_insert("exceptions", _ALLOWED_INSERT, data)
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
            f"UPDATE exceptions SET {set_clause}, updated_at = NOW() "
            f"WHERE id = ${len(values)} RETURNING *"
        )
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(q, *values)
        return self._row(row)

    async def soft_delete(self, id: str | uuid.UUID) -> bool:
        raise NotImplementedError(
            "Exceptions are not deleted; use update() to transition status instead."
        )

    async def get_by_finding_id(
        self, finding_id: str | uuid.UUID
    ) -> list[dict[str, Any]]:
        """Return all exceptions for a given finding, newest first."""
        q = (
            "SELECT * FROM exceptions WHERE finding_id = $1 "
            "ORDER BY created_at DESC"
        )
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(q, uuid.UUID(str(finding_id)))
        return self._rows(rows)

    async def check_existing_pending(
        self, finding_id: str | uuid.UUID
    ) -> dict[str, Any] | None:
        """Return the first pending/requested exception for a finding, or None."""
        q = (
            "SELECT * FROM exceptions "
            "WHERE finding_id = $1 AND status IN ('pending', 'requested') "
            "ORDER BY created_at DESC LIMIT 1"
        )
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(q, uuid.UUID(str(finding_id)))
        return self._row(row)

    async def check_existing_approved_active(
        self, finding_id: str | uuid.UUID
    ) -> dict[str, Any] | None:
        """Return an active approved exception (not expired), or None."""
        q = (
            "SELECT * FROM exceptions "
            "WHERE finding_id = $1 AND status = 'approved' "
            "AND expires_at > NOW() "
            "ORDER BY expires_at DESC LIMIT 1"
        )
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(q, uuid.UUID(str(finding_id)))
        return self._row(row)

    async def list_pending_by_approver_role(
        self, approver_role: str
    ) -> list[dict[str, Any]]:
        """Return pending exceptions routed to a specific approver role."""
        q = (
            "SELECT * FROM exceptions "
            "WHERE approver_role = $1 AND status IN ('pending', 'requested') "
            "ORDER BY created_at ASC"
        )
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(q, approver_role)
        return self._rows(rows)

    async def list_expired_for_processing(
        self, *, batch_size: int = 50
    ) -> list[dict[str, Any]]:
        """Return approved exceptions whose expires_at has passed, up to batch_size.

        Uses the database server clock (NOW()) to avoid application clock skew.
        Idempotent: only returns status='approved' rows — already-expired rows
        are excluded because their status will have been updated to 'expired'.
        """
        q = (
            "SELECT * FROM exceptions "
            "WHERE status = 'approved' AND expires_at < NOW() "
            "ORDER BY expires_at ASC "
            "LIMIT $1"
        )
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(q, batch_size)
        return self._rows(rows)

    async def expire(self, id: str | uuid.UUID) -> dict[str, Any] | None:
        """Transition an exception status from 'approved' to 'expired'.

        Uses a WHERE clause guard to ensure idempotency: the update is a no-op
        if the exception is already in a non-approved state.
        """
        q = (
            "UPDATE exceptions "
            "SET status = 'expired', updated_at = NOW() "
            "WHERE id = $1 AND status = 'approved' "
            "RETURNING *"
        )
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(q, uuid.UUID(str(id)))
        return self._row(row)

    async def update_decision(
        self,
        id: str | uuid.UUID,
        *,
        status: str,
        decided_by: uuid.UUID | None,
        decided_at: datetime,
        decision_comment: str,
    ) -> dict[str, Any] | None:
        """Atomically record an approve/deny decision on a pending exception.

        Only updates rows whose current status is 'pending' to prevent
        double-decision races.  Returns None if no row matched (already decided).
        """
        q = (
            "UPDATE exceptions "
            "SET status = $1, decided_by = $2, decided_at = $3, "
            "decision_comment = $4, updated_at = NOW() "
            "WHERE id = $5 AND status = 'pending' "
            "RETURNING *"
        )
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                q, status, decided_by, decided_at, decision_comment, uuid.UUID(str(id))
            )
        return self._row(row)

    async def list_by_status_and_role(
        self,
        *,
        status: str | None = None,
        approver_role: str | None = None,
        cursor: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Return exceptions filtered by status and/or approver_role.

        Cursor-based pagination using (created_at DESC, id DESC).
        Pass the last row's ``{created_at.isoformat()}:{id}`` as *cursor*.
        """
        params: list[Any] = []
        idx = 1
        q = "SELECT * FROM exceptions WHERE TRUE"

        if status:
            q += f" AND status = ${idx}"
            params.append(status)
            idx += 1

        if approver_role:
            q += f" AND approver_role = ${idx}"
            params.append(approver_role)
            idx += 1

        if cursor:
            try:
                ts_part, id_part = cursor.rsplit(":", 1)
                q += f" AND (created_at, id) < (${idx}::timestamptz, ${idx + 1})"
                params.append(ts_part)
                params.append(uuid.UUID(id_part))
                idx += 2
            except (ValueError, AttributeError):
                logger.warning(
                    "exceptions.list_by_status_and_role.invalid_cursor", cursor=cursor
                )

        q += f" ORDER BY created_at DESC, id DESC LIMIT ${idx}"
        params.append(limit)

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(q, *params)
        return self._rows(rows)

    async def count_by_status_and_role(
        self,
        *,
        status: str | None = None,
        approver_role: str | None = None,
    ) -> int:
        """Return the total count of exceptions matching the given filters."""
        params: list[Any] = []
        idx = 1
        q = "SELECT COUNT(*) FROM exceptions WHERE TRUE"

        if status:
            q += f" AND status = ${idx}"
            params.append(status)
            idx += 1

        if approver_role:
            q += f" AND approver_role = ${idx}"
            params.append(approver_role)
            idx += 1

        async with self._pool.acquire() as conn:
            count = await conn.fetchval(q, *params)
        return int(count or 0)
