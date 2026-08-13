"""RemediationRecommendationRepository: async CRUD for remediation_recommendations."""

from __future__ import annotations

import uuid
from typing import Any

import structlog

from forgeguard.data.repositories.base import BaseRepository

logger = structlog.get_logger(__name__)

_ALLOWED_INSERT: frozenset[str] = frozenset({
    "id",
    "finding_id",
    "recommendation_text",
    "implementation_guide",
    "business_impact",
    "confidence_score",
    "source",
})

_ALLOWED_UPDATE: frozenset[str] = frozenset({
    "recommendation_text",
    "implementation_guide",
    "confidence_score",
    "source",
})


class RemediationRecommendationRepository(BaseRepository):
    """Async repository for the remediation_recommendations table."""

    _table = "remediation_recommendations"

    async def get_by_id(
        self, id: str | uuid.UUID, *, include_deleted: bool = False
    ) -> dict[str, Any] | None:
        q = "SELECT * FROM remediation_recommendations WHERE id = $1"
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
        q = "SELECT * FROM remediation_recommendations WHERE TRUE"
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
        query, values = self._safe_insert(
            "remediation_recommendations", _ALLOWED_INSERT, data
        )
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
            f"UPDATE remediation_recommendations SET {set_clause} "
            f"WHERE id = ${len(values)} RETURNING *"
        )
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(q, *values)
        return self._row(row)

    async def soft_delete(self, id: str | uuid.UUID) -> bool:
        raise NotImplementedError(
            "Remediation recommendations are removed via CASCADE when the finding is deleted"
        )

    async def get_by_finding_id(
        self, finding_id: str | uuid.UUID
    ) -> list[dict[str, Any]]:
        q = (
            "SELECT * FROM remediation_recommendations "
            "WHERE finding_id = $1 ORDER BY created_at"
        )
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(q, uuid.UUID(str(finding_id)))
        return self._rows(rows)

    async def get_latest_by_finding_id(
        self, finding_id: str | uuid.UUID
    ) -> dict[str, Any] | None:
        q = (
            "SELECT * FROM remediation_recommendations "
            "WHERE finding_id = $1 ORDER BY created_at DESC LIMIT 1"
        )
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(q, uuid.UUID(str(finding_id)))
        return self._row(row)

    async def upsert(
        self,
        finding_id: str | uuid.UUID,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """Insert a recommendation or replace the existing one for the same finding.

        Uses INSERT … ON CONFLICT (finding_id) DO UPDATE to avoid duplicate rows
        when concurrent requests generate recommendations for the same finding.
        """
        data = {**data, "finding_id": uuid.UUID(str(finding_id))}
        filtered = [(col, val) for col, val in data.items() if col in _ALLOWED_INSERT]
        if not filtered:
            raise ValueError("No allowed columns found for upsert")
        col_names = ", ".join(col for col, _ in filtered)
        placeholders = ", ".join(f"${i + 1}" for i in range(len(filtered)))
        values = [val for _, val in filtered]
        update_cols = [
            col for col, _ in filtered
            if col not in ("id", "finding_id")
        ]
        if not update_cols:
            raise ValueError("No updatable columns found for upsert")
        update_clause = ", ".join(
            f"{col} = EXCLUDED.{col}" for col in update_cols
        )
        q = (
            f"INSERT INTO remediation_recommendations ({col_names}) "
            f"VALUES ({placeholders}) "
            "ON CONFLICT (finding_id) DO UPDATE SET "
            f"{update_clause} RETURNING *"
        )
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(q, *values)
        return dict(row)  # type: ignore[arg-type]

    async def get_by_assessment(
        self, assessment_id: str | uuid.UUID
    ) -> list[dict[str, Any]]:
        q = (
            "SELECT rr.* FROM remediation_recommendations rr "
            "JOIN findings f ON rr.finding_id = f.id "
            "WHERE f.assessment_id = $1 ORDER BY rr.created_at"
        )
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(q, uuid.UUID(str(assessment_id)))
        return self._rows(rows)
