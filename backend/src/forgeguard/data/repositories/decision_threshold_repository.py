"""DecisionThresholdRepository: CRUD for configurable decision threshold records.

The partial unique index on (is_active) WHERE is_active = true enforces the
single-active-config invariant at the database level.  The activate() method
uses a single transaction to deactivate the previous active config and activate
the target row atomically, preventing race conditions.
"""

from __future__ import annotations

import uuid
from typing import Any

import asyncpg
import structlog

from forgeguard.data.repositories.base import BaseRepository

logger = structlog.get_logger(__name__)

_ALLOWED_INSERT: frozenset[str] = frozenset({
    "id",
    "name",
    "approve_health_min",
    "approve_risk_max",
    "conditional_health_min",
    "conditional_risk_max",
    "is_active",
    "created_by",
    "updated_by",
})

_ALLOWED_UPDATE: frozenset[str] = frozenset({
    "name",
    "approve_health_min",
    "approve_risk_max",
    "conditional_health_min",
    "conditional_risk_max",
    "updated_by",
    "updated_at",
})


class DecisionThresholdRepository(BaseRepository):
    _table = "decision_thresholds"

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    async def get_by_id(
        self, id: str | uuid.UUID, *, include_deleted: bool = False
    ) -> dict[str, Any] | None:
        q = "SELECT * FROM decision_thresholds WHERE id = $1"
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(q, uuid.UUID(str(id)))
        return self._row(row)

    async def get_active(self) -> dict[str, Any] | None:
        """Return the currently active threshold configuration, or None."""
        q = "SELECT * FROM decision_thresholds WHERE is_active = true LIMIT 1"
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(q)
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
        q = "SELECT * FROM decision_thresholds WHERE TRUE"
        if cursor:
            q += f" AND created_at < ${idx}"
            params.append(cursor)
            idx += 1
        q += f" ORDER BY created_at DESC LIMIT ${idx}"
        params.append(limit)
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(q, *params)
        return self._rows(rows)

    async def count_all(self) -> int:
        q = "SELECT COUNT(*) FROM decision_thresholds"
        async with self._pool.acquire() as conn:
            return await conn.fetchval(q)

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    async def create(self, data: dict[str, Any]) -> dict[str, Any]:
        query, values = self._safe_insert("decision_thresholds", _ALLOWED_INSERT, data)
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
            f"UPDATE decision_thresholds SET {set_clause}, updated_at = now() "
            f"WHERE id = ${len(values)} RETURNING *"
        )
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(q, *values)
        return self._row(row)

    async def activate(self, id: str | uuid.UUID) -> dict[str, Any] | None:
        """Atomically deactivate the current active config and activate *id*.

        Runs inside a single serialisable transaction so no window exists
        between the two UPDATEs where two configs could both be active.
        """
        target_id = uuid.UUID(str(id))
        async with self._pool.acquire() as conn:
            async with conn.transaction(isolation="serializable"):
                # Clear any existing active config.
                await conn.execute(
                    "UPDATE decision_thresholds SET is_active = false, updated_at = now() "
                    "WHERE is_active = true"
                )
                # Activate the target row.
                row = await conn.fetchrow(
                    "UPDATE decision_thresholds SET is_active = true, updated_at = now() "
                    "WHERE id = $1 RETURNING *",
                    target_id,
                )
        return self._row(row)

    async def deactivate(self, id: str | uuid.UUID) -> dict[str, Any] | None:
        target_id = uuid.UUID(str(id))
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "UPDATE decision_thresholds SET is_active = false, updated_at = now() "
                "WHERE id = $1 RETURNING *",
                target_id,
            )
        return self._row(row)

    async def soft_delete(self, id: str | uuid.UUID) -> bool:
        raise NotImplementedError(
            "decision_thresholds does not support soft delete — "
            "use deactivate() to disable a config"
        )
