"""ScoreRepository: async access to assessment_scores (append-only, no update)."""

from __future__ import annotations

import json
import uuid
from decimal import Decimal
from typing import Any

import asyncpg
import structlog

from forgeguard.data.repositories.base import BaseRepository

logger = structlog.get_logger(__name__)

_ALLOWED_INSERT: frozenset[str] = frozenset({
    "id", "assessment_id", "service_id", "score_type",
    "overall_score", "dimension_scores", "contributing_factors", "weights_used",
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

    async def list_scores_by_service(
        self,
        service_id: str | uuid.UUID,
        score_type: str = "health",
        *,
        cursor: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Return scores for a service, cursor-paginated by (created_at DESC, id DESC).

        Pass the last row's ``<iso_created_at>:<uuid>`` as *cursor* for next page.
        """
        params: list[Any] = [uuid.UUID(str(service_id)), score_type]
        idx = 3
        q = (
            "SELECT * FROM assessment_scores "
            "WHERE service_id = $1 AND score_type = $2"
        )
        if cursor:
            try:
                ts_part, id_part = cursor.rsplit(":", 1)
                q += f" AND (created_at, id) < (${idx}::timestamptz, ${idx + 1})"
                params.append(ts_part)
                params.append(uuid.UUID(id_part))
                idx += 2
            except (ValueError, AttributeError):
                logger.warning("score_repository.invalid_cursor", cursor=cursor)

        q += f" ORDER BY created_at DESC, id DESC LIMIT ${idx}"
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

    async def save_health_score(
        self,
        result: Any,  # HealthScoreResult — avoid circular import by using Any
        assessment_id: uuid.UUID,
        service_id: uuid.UUID,
    ) -> dict[str, Any]:
        """Persist a HealthScoreResult to the assessment_scores table.

        Serialises dimension_scores and weights_used to JSONB.
        Returns the inserted row as a dict.
        """
        dimension_scores_payload: dict[str, Any] = {
            dim: {
                "dimension": ds.dimension,
                "score": float(ds.score) if ds.score is not None else None,
                "total_rules": ds.total_rules,
                "passed_rules": ds.passed_rules,
                "failed_rules": ds.failed_rules,
                "inconclusive_rules": ds.inconclusive_rules,
                "error_rules": ds.error_rules,
                "has_data": ds.has_data,
            }
            for dim, ds in result.dimension_scores.items()
        }

        weights_payload: dict[str, Any] = {
            dim: float(w) for dim, w in result.weights_used.items()
        }

        overall = (
            Decimal(str(result.overall_score))
            if result.overall_score is not None
            else None
        )

        data: dict[str, Any] = {
            "id": uuid.uuid4(),
            "assessment_id": assessment_id,
            "service_id": service_id,
            "score_type": "health",
            "overall_score": overall,
            "dimension_scores": json.dumps(dimension_scores_payload),
            "weights_used": json.dumps(weights_payload),
        }

        row = await self.create(data)
        logger.info(
            "score_repository.health_score_saved",
            assessment_id=str(assessment_id),
            service_id=str(service_id),
            overall_score=str(result.overall_score),
        )
        return row

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

    async def get_latest_health_score(
        self, service_id: str | uuid.UUID
    ) -> dict[str, Any] | None:
        """Return the most recent health score for a service."""
        return await self.get_latest_score(service_id, "health")

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
