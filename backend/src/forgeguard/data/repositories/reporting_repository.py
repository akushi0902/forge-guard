"""ReportingRepository: database-level aggregation queries for compliance reports (WO-093).

All queries use database-level aggregation (SUM, AVG, COUNT, GROUP BY) to
avoid loading individual rows into Python memory.  All SQL values are passed
as asyncpg positional parameters — zero string interpolation of user input.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any, Optional

import asyncpg
import structlog

logger = structlog.get_logger(__name__)


class ReportingRepository:
    """Async aggregation queries across assessment_scores, findings, and exceptions."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    # ------------------------------------------------------------------
    # Health score trends (weekly averages per service)
    # ------------------------------------------------------------------

    async def get_health_score_trends(
        self,
        start_date: date,
        end_date: date,
        service_id: Optional[uuid.UUID] = None,
    ) -> list[dict[str, Any]]:
        """Return weekly avg health scores per service within the date range.

        Groups by service_id and date_trunc('week', created_at).
        Returns rows: {service_id, service_name, week_start, avg_score, dimension_scores}.
        """
        params: list[Any] = [start_date, end_date]
        service_filter = ""
        if service_id is not None:
            service_filter = " AND s.id = $3"
            params.append(service_id)

        q = f"""
            SELECT
                s.id AS service_id,
                s.name AS service_name,
                date_trunc('week', sc.created_at)::date AS week_start,
                AVG(sc.overall_score) AS avg_score,
                jsonb_object_agg(
                    dim_key,
                    dim_avg
                ) AS dimension_scores
            FROM assessment_scores sc
            JOIN services s ON s.id = sc.service_id
            CROSS JOIN LATERAL (
                SELECT
                    key AS dim_key,
                    AVG((value::text)::numeric) AS dim_avg
                FROM jsonb_each(sc.dimension_scores)
                GROUP BY key
            ) dims
            WHERE sc.score_type = 'health'
              AND sc.created_at::date >= $1
              AND sc.created_at::date <= $2
              AND s.deleted_at IS NULL
              {service_filter}
            GROUP BY s.id, s.name, date_trunc('week', sc.created_at)
            ORDER BY s.name, week_start
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(q, *params)
        return [dict(r) for r in rows]

    async def get_health_score_trends_simple(
        self,
        start_date: date,
        end_date: date,
        service_id: Optional[uuid.UUID] = None,
    ) -> list[dict[str, Any]]:
        """Simplified weekly avg health scores — no per-dimension breakdown.

        Falls back to this when the LATERAL/jsonb aggregation is unavailable.
        Returns rows: {service_id, service_name, week_start, avg_score}.
        """
        params: list[Any] = [start_date, end_date]
        service_filter = ""
        if service_id is not None:
            service_filter = " AND s.id = $3"
            params.append(service_id)

        q = f"""
            SELECT
                s.id AS service_id,
                s.name AS service_name,
                date_trunc('week', sc.created_at)::date AS week_start,
                AVG(sc.overall_score) AS avg_score,
                sc.dimension_scores
            FROM assessment_scores sc
            JOIN services s ON s.id = sc.service_id
            WHERE sc.score_type = 'health'
              AND sc.created_at::date >= $1
              AND sc.created_at::date <= $2
              AND s.deleted_at IS NULL
              {service_filter}
            GROUP BY s.id, s.name, date_trunc('week', sc.created_at), sc.dimension_scores
            ORDER BY s.name, week_start
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(q, *params)
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Findings summary
    # ------------------------------------------------------------------

    async def get_findings_summary(
        self,
        start_date: date,
        end_date: date,
        service_id: Optional[uuid.UUID] = None,
    ) -> list[dict[str, Any]]:
        """Count findings by severity and status within the date range.

        Returns rows: {severity, status, count}.
        Includes findings created within the range.
        """
        params: list[Any] = [start_date, end_date]
        service_filter = ""
        if service_id is not None:
            service_filter = " AND f.service_id = $3"
            params.append(service_id)

        q = f"""
            SELECT
                f.severity,
                f.status,
                COUNT(*) AS count
            FROM findings f
            JOIN services s ON s.id = f.service_id
            WHERE f.created_at::date >= $1
              AND f.created_at::date <= $2
              AND s.deleted_at IS NULL
              {service_filter}
            GROUP BY f.severity, f.status
            ORDER BY f.severity, f.status
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(q, *params)
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Remediation metrics (mean TTR for resolved findings)
    # ------------------------------------------------------------------

    async def get_remediation_metrics(
        self,
        start_date: date,
        end_date: date,
        service_id: Optional[uuid.UUID] = None,
    ) -> dict[str, Any]:
        """Compute mean time-to-remediation for findings resolved in the date range.

        Excludes findings with NULL resolved_at (still open).
        Returns: {mean_ttr_seconds, findings_resolved, findings_open}.
        """
        params: list[Any] = [start_date, end_date]
        service_filter = ""
        if service_id is not None:
            service_filter = " AND f.service_id = $3"
            params.append(service_id)

        q = f"""
            SELECT
                AVG(EXTRACT(EPOCH FROM (f.resolved_at - f.created_at))) AS mean_ttr_seconds,
                COUNT(*) FILTER (WHERE f.resolved_at IS NOT NULL) AS findings_resolved,
                COUNT(*) FILTER (WHERE f.resolved_at IS NULL AND f.status = 'open') AS findings_open
            FROM findings f
            JOIN services s ON s.id = f.service_id
            WHERE f.created_at::date >= $1
              AND f.created_at::date <= $2
              AND s.deleted_at IS NULL
              {service_filter}
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(q, *params)
        return dict(row) if row else {}

    # ------------------------------------------------------------------
    # Exceptions summary
    # ------------------------------------------------------------------

    async def get_exceptions_summary(
        self,
        start_date: date,
        end_date: date,
        service_id: Optional[uuid.UUID] = None,
    ) -> list[dict[str, Any]]:
        """Count exceptions by status where expires_at falls within the date range.

        Returns rows: {status, count}.
        """
        params: list[Any] = [start_date, end_date]
        service_filter = ""
        if service_id is not None:
            service_filter = " AND f.service_id = $3"
            params.append(service_id)

        q = f"""
            SELECT
                e.status,
                COUNT(*) AS count
            FROM exceptions e
            JOIN findings f ON f.id = e.finding_id
            JOIN services s ON s.id = f.service_id
            WHERE e.expires_at::date >= $1
              AND e.expires_at::date <= $2
              AND s.deleted_at IS NULL
              {service_filter}
            GROUP BY e.status
            ORDER BY e.status
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(q, *params)
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Service existence check
    # ------------------------------------------------------------------

    async def service_exists(self, service_id: uuid.UUID) -> bool:
        """Return True if service exists and is not soft-deleted."""
        q = "SELECT 1 FROM services WHERE id = $1 AND deleted_at IS NULL"
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(q, service_id)
        return row is not None
