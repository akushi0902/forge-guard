"""RetentionService: automated data retention purge for all six data categories.

Enforces ForgeGuard's data lifecycle policies:
  - audit_logs          365 days  — partition DROP (DDL)
  - assessment_scores   180 days  — cryptographic erasure + DELETE
  - findings            180 days  — CASCADE DELETE
  - release_decisions   365 days  — cryptographic erasure + DELETE
  - ai_conversations     90 days  — physical DELETE
  - exceptions (post-expiry) 30 days after expires_at — physical DELETE

Design:
  - All cutoff timestamps use the database server clock (NOW()) to avoid clock
    skew between the application and DB servers.
  - Purge jobs capture the cutoff BEFORE starting so the job's own audit records
    are not purged in the same run.
  - Row-level purges use batched DELETE (1000 per batch) with brief sleeps to
    prevent lock contention during normal operations.
  - Each purge method is idempotent — safe to re-run if interrupted.
  - Every purge execution produces an audit record via AuditService if available.
  - Failures are caught per-method; the scheduler retries on the next run.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

import asyncpg
import structlog

from forgeguard.utils.crypto_erasure import (
    cryptographic_erase_jsonb,
    cryptographic_erase_text,
)

if TYPE_CHECKING:
    from forgeguard.services.audit import AuditService

logger = structlog.get_logger(__name__)

_BATCH_SIZE = 1000
_BATCH_SLEEP_SECONDS = 0.01


@dataclass
class PurgeResult:
    """Outcome of a single purge execution."""

    category: str
    records_affected: int
    duration_ms: float
    status: str  # "success" | "failure"
    error_message: Optional[str] = None
    partitions_dropped: list[str] = field(default_factory=list)
    partitions_created: list[str] = field(default_factory=list)


class RetentionService:
    """Orchestrates all data retention purge operations.

    Args:
        pool:          asyncpg connection pool.
        audit_service: Optional AuditService for writing purge audit records.
                       When None, audit logging is skipped (best-effort).
        retention_audit_days:           Days to retain audit logs (default 365).
        retention_assessment_days:      Days to retain assessment scores (default 180).
        retention_findings_days:        Days to retain findings (default 180).
        retention_release_decisions_days: Days to retain release decisions (default 365).
        retention_ai_conversations_days: Days to retain AI conversations (default 90).
        retention_exceptions_days:      Days after expires_at to purge exceptions (default 30).
    """

    def __init__(
        self,
        pool: asyncpg.Pool,
        audit_service: Optional["AuditService"] = None,
        *,
        retention_audit_days: int = 365,
        retention_assessment_days: int = 180,
        retention_findings_days: int = 180,
        retention_release_decisions_days: int = 365,
        retention_ai_conversations_days: int = 90,
        retention_exceptions_days: int = 30,
    ) -> None:
        self._pool = pool
        self._audit_service = audit_service
        self._retention_audit_days = retention_audit_days
        self._retention_assessment_days = retention_assessment_days
        self._retention_findings_days = retention_findings_days
        self._retention_release_decisions_days = retention_release_decisions_days
        self._retention_ai_conversations_days = retention_ai_conversations_days
        self._retention_exceptions_days = retention_exceptions_days

    # ------------------------------------------------------------------
    # Public purge methods
    # ------------------------------------------------------------------

    async def purge_audit_logs(self) -> PurgeResult:
        """Drop monthly audit_logs partitions older than the retention period.

        Calls the existing PL/pgSQL function ``drop_expired_audit_partitions``
        deployed by migration 0002.  Does NOT use row-by-row DELETE.
        """
        start = time.monotonic()
        try:
            async with self._pool.acquire() as conn:
                dropped_count: int = await conn.fetchval(
                    "SELECT drop_expired_audit_partitions($1)",
                    self._retention_audit_days,
                )

            duration_ms = (time.monotonic() - start) * 1000
            result = PurgeResult(
                category="audit_logs",
                records_affected=dropped_count or 0,
                duration_ms=duration_ms,
                status="success",
            )
            logger.info(
                "retention.audit_logs.purged",
                partitions_dropped=dropped_count,
                duration_ms=round(duration_ms, 1),
            )
            await self._write_audit_record(result)
            return result

        except Exception as exc:
            duration_ms = (time.monotonic() - start) * 1000
            logger.error(
                "retention.audit_logs.failed",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            result = PurgeResult(
                category="audit_logs",
                records_affected=0,
                duration_ms=duration_ms,
                status="failure",
                error_message=str(exc),
            )
            await self._write_audit_record(result)
            return result

    async def purge_assessments(self) -> PurgeResult:
        """Cryptographically erase JSONB fields then DELETE expired assessment_scores.

        Records older than ``retention_assessment_days`` are processed in batches
        of 1000.  Each batch erases ``dimension_scores`` and ``contributing_factors``
        before deletion to prevent recovery from WAL.
        """
        start = time.monotonic()
        total_deleted = 0
        try:
            # Capture cutoff from DB server clock once before starting.
            async with self._pool.acquire() as conn:
                cutoff: datetime = await conn.fetchval(
                    "SELECT NOW() - ($1 * INTERVAL '1 day')",
                    self._retention_assessment_days,
                )

            while True:
                async with self._pool.acquire() as conn:
                    async with conn.transaction(isolation="read_committed"):
                        rows = await conn.fetch(
                            "SELECT id FROM assessment_scores WHERE created_at < $1 LIMIT $2",
                            cutoff,
                            _BATCH_SIZE,
                        )
                        if not rows:
                            break
                        ids = [r["id"] for r in rows]
                        erased = await cryptographic_erase_jsonb(
                            conn,
                            table="assessment_scores",
                            id_column="id",
                            jsonb_columns=["dimension_scores", "contributing_factors"],
                            record_ids=ids,
                        )
                        deleted = await conn.fetchval(
                            "WITH deleted AS ("
                            "  DELETE FROM assessment_scores WHERE id = ANY($1::uuid[]) RETURNING 1"
                            ") SELECT count(*) FROM deleted",
                            ids,
                        )
                        total_deleted += int(deleted or 0)

                if len(rows) < _BATCH_SIZE:
                    break
                await asyncio.sleep(_BATCH_SLEEP_SECONDS)

            duration_ms = (time.monotonic() - start) * 1000
            result = PurgeResult(
                category="assessment_scores",
                records_affected=total_deleted,
                duration_ms=duration_ms,
                status="success",
            )
            logger.info(
                "retention.assessments.purged",
                records_deleted=total_deleted,
                duration_ms=round(duration_ms, 1),
            )
            await self._write_audit_record(result)
            return result

        except Exception as exc:
            duration_ms = (time.monotonic() - start) * 1000
            logger.error("retention.assessments.failed", error=str(exc))
            result = PurgeResult(
                category="assessment_scores",
                records_affected=total_deleted,
                duration_ms=duration_ms,
                status="failure",
                error_message=str(exc),
            )
            await self._write_audit_record(result)
            return result

    async def purge_findings(self) -> PurgeResult:
        """DELETE expired findings — CASCADE drops remediation_recommendations.

        Records older than ``retention_findings_days`` are deleted in batches.
        The ON DELETE CASCADE from findings to remediation_recommendations
        handles cleanup of recommendations automatically.
        """
        start = time.monotonic()
        total_deleted = 0
        try:
            async with self._pool.acquire() as conn:
                cutoff = await conn.fetchval(
                    "SELECT NOW() - ($1 * INTERVAL '1 day')",
                    self._retention_findings_days,
                )

            while True:
                async with self._pool.acquire() as conn:
                    async with conn.transaction(isolation="read_committed"):
                        deleted = await conn.fetchval(
                            "WITH deleted AS ("
                            "  DELETE FROM findings WHERE id IN ("
                            "    SELECT id FROM findings WHERE created_at < $1 LIMIT $2"
                            "  ) RETURNING 1"
                            ") SELECT count(*) FROM deleted",
                            cutoff,
                            _BATCH_SIZE,
                        )
                        batch_deleted = int(deleted or 0)
                        total_deleted += batch_deleted

                if batch_deleted < _BATCH_SIZE:
                    break
                await asyncio.sleep(_BATCH_SLEEP_SECONDS)

            duration_ms = (time.monotonic() - start) * 1000
            result = PurgeResult(
                category="findings",
                records_affected=total_deleted,
                duration_ms=duration_ms,
                status="success",
            )
            logger.info(
                "retention.findings.purged",
                records_deleted=total_deleted,
                duration_ms=round(duration_ms, 1),
            )
            await self._write_audit_record(result)
            return result

        except Exception as exc:
            duration_ms = (time.monotonic() - start) * 1000
            logger.error("retention.findings.failed", error=str(exc))
            result = PurgeResult(
                category="findings",
                records_affected=total_deleted,
                duration_ms=duration_ms,
                status="failure",
                error_message=str(exc),
            )
            await self._write_audit_record(result)
            return result

    async def purge_release_decisions(self) -> PurgeResult:
        """Cryptographically erase rationale/comment then DELETE expired release_decisions.

        Records older than ``retention_release_decisions_days`` have their TEXT
        fields overwritten before deletion.
        """
        start = time.monotonic()
        total_deleted = 0
        try:
            async with self._pool.acquire() as conn:
                cutoff = await conn.fetchval(
                    "SELECT NOW() - ($1 * INTERVAL '1 day')",
                    self._retention_release_decisions_days,
                )

            while True:
                async with self._pool.acquire() as conn:
                    async with conn.transaction(isolation="read_committed"):
                        rows = await conn.fetch(
                            "SELECT id FROM release_decisions WHERE created_at < $1 LIMIT $2",
                            cutoff,
                            _BATCH_SIZE,
                        )
                        if not rows:
                            break
                        ids = [r["id"] for r in rows]
                        await cryptographic_erase_text(
                            conn,
                            table="release_decisions",
                            id_column="id",
                            text_columns=["rationale", "comment"],
                            record_ids=ids,
                        )
                        deleted = await conn.fetchval(
                            "WITH deleted AS ("
                            "  DELETE FROM release_decisions WHERE id = ANY($1::uuid[]) RETURNING 1"
                            ") SELECT count(*) FROM deleted",
                            ids,
                        )
                        total_deleted += int(deleted or 0)

                if len(rows) < _BATCH_SIZE:
                    break
                await asyncio.sleep(_BATCH_SLEEP_SECONDS)

            duration_ms = (time.monotonic() - start) * 1000
            result = PurgeResult(
                category="release_decisions",
                records_affected=total_deleted,
                duration_ms=duration_ms,
                status="success",
            )
            logger.info(
                "retention.release_decisions.purged",
                records_deleted=total_deleted,
                duration_ms=round(duration_ms, 1),
            )
            await self._write_audit_record(result)
            return result

        except Exception as exc:
            duration_ms = (time.monotonic() - start) * 1000
            logger.error("retention.release_decisions.failed", error=str(exc))
            result = PurgeResult(
                category="release_decisions",
                records_affected=total_deleted,
                duration_ms=duration_ms,
                status="failure",
                error_message=str(exc),
            )
            await self._write_audit_record(result)
            return result

    async def purge_ai_conversations(self) -> PurgeResult:
        """DELETE ai_conversations older than retention_ai_conversations_days."""
        start = time.monotonic()
        total_deleted = 0
        try:
            async with self._pool.acquire() as conn:
                cutoff = await conn.fetchval(
                    "SELECT NOW() - ($1 * INTERVAL '1 day')",
                    self._retention_ai_conversations_days,
                )

            while True:
                async with self._pool.acquire() as conn:
                    async with conn.transaction(isolation="read_committed"):
                        deleted = await conn.fetchval(
                            "WITH deleted AS ("
                            "  DELETE FROM ai_conversations WHERE id IN ("
                            "    SELECT id FROM ai_conversations"
                            "    WHERE created_at < $1 LIMIT $2"
                            "  ) RETURNING 1"
                            ") SELECT count(*) FROM deleted",
                            cutoff,
                            _BATCH_SIZE,
                        )
                        batch_deleted = int(deleted or 0)
                        total_deleted += batch_deleted

                if batch_deleted < _BATCH_SIZE:
                    break
                await asyncio.sleep(_BATCH_SLEEP_SECONDS)

            duration_ms = (time.monotonic() - start) * 1000
            result = PurgeResult(
                category="ai_conversations",
                records_affected=total_deleted,
                duration_ms=duration_ms,
                status="success",
            )
            logger.info(
                "retention.ai_conversations.purged",
                records_deleted=total_deleted,
                duration_ms=round(duration_ms, 1),
            )
            await self._write_audit_record(result)
            return result

        except Exception as exc:
            duration_ms = (time.monotonic() - start) * 1000
            logger.error("retention.ai_conversations.failed", error=str(exc))
            result = PurgeResult(
                category="ai_conversations",
                records_affected=total_deleted,
                duration_ms=duration_ms,
                status="failure",
                error_message=str(exc),
            )
            await self._write_audit_record(result)
            return result

    async def purge_expired_exceptions(self) -> PurgeResult:
        """DELETE exceptions that expired more than retention_exceptions_days ago."""
        start = time.monotonic()
        total_deleted = 0
        try:
            async with self._pool.acquire() as conn:
                # Cutoff = exceptions whose expires_at was more than N days ago.
                cutoff = await conn.fetchval(
                    "SELECT NOW() - ($1 * INTERVAL '1 day')",
                    self._retention_exceptions_days,
                )

            while True:
                async with self._pool.acquire() as conn:
                    async with conn.transaction(isolation="read_committed"):
                        deleted = await conn.fetchval(
                            "WITH deleted AS ("
                            "  DELETE FROM exceptions WHERE id IN ("
                            "    SELECT id FROM exceptions"
                            "    WHERE expires_at < $1 LIMIT $2"
                            "  ) RETURNING 1"
                            ") SELECT count(*) FROM deleted",
                            cutoff,
                            _BATCH_SIZE,
                        )
                        batch_deleted = int(deleted or 0)
                        total_deleted += batch_deleted

                if batch_deleted < _BATCH_SIZE:
                    break
                await asyncio.sleep(_BATCH_SLEEP_SECONDS)

            duration_ms = (time.monotonic() - start) * 1000
            result = PurgeResult(
                category="exceptions",
                records_affected=total_deleted,
                duration_ms=duration_ms,
                status="success",
            )
            logger.info(
                "retention.exceptions.purged",
                records_deleted=total_deleted,
                duration_ms=round(duration_ms, 1),
            )
            await self._write_audit_record(result)
            return result

        except Exception as exc:
            duration_ms = (time.monotonic() - start) * 1000
            logger.error("retention.exceptions.failed", error=str(exc))
            result = PurgeResult(
                category="exceptions",
                records_affected=total_deleted,
                duration_ms=duration_ms,
                status="failure",
                error_message=str(exc),
            )
            await self._write_audit_record(result)
            return result

    # ------------------------------------------------------------------
    # Partition lifecycle
    # ------------------------------------------------------------------

    async def create_next_partition(self) -> str:
        """Create the next calendar month's audit_logs partition if not present.

        Calls the PL/pgSQL ``create_audit_partition`` function deployed by
        migration 0002.  Idempotent — a no-op if the partition already exists.

        Returns:
            Partition name that was created (or already existed).
        """
        from datetime import date  # noqa: PLC0415

        today = date.today()
        if today.month == 12:
            next_year, next_month = today.year + 1, 1
        else:
            next_year, next_month = today.year, today.month + 1
        next_month_start = date(next_year, next_month, 1)
        partition_name = f"audit_logs_{next_year:04d}_{next_month:02d}"

        try:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    "SELECT create_audit_partition($1::date)",
                    next_month_start,
                )
            logger.info(
                "retention.partition.created",
                partition=partition_name,
            )
        except Exception as exc:
            logger.warning(
                "retention.partition.create_failed",
                partition=partition_name,
                error=str(exc),
            )

        return partition_name

    async def drop_expired_partitions(self) -> list[str]:
        """Drop audit_logs partitions older than the retention period.

        Calls the PL/pgSQL ``drop_expired_audit_partitions`` function and
        returns the names of partitions identified as expired (by listing them
        before the drop).

        Returns:
            List of partition names that were candidates for dropping.
        """
        import re  # noqa: PLC0415
        from datetime import date, timedelta  # noqa: PLC0415

        try:
            async with self._pool.acquire() as conn:
                # List partition names before dropping.
                rows = await conn.fetch(
                    """
                    SELECT c.relname AS partition_name
                    FROM pg_catalog.pg_class p
                    JOIN pg_catalog.pg_inherits i ON i.inhparent = p.oid
                    JOIN pg_catalog.pg_class c ON c.oid = i.inhrelid
                    JOIN pg_catalog.pg_namespace n ON n.oid = p.relnamespace
                    WHERE p.relname = 'audit_logs'
                      AND n.nspname = current_schema()
                    ORDER BY c.relname
                    """
                )
                all_partitions = [r["partition_name"] for r in rows]

                # Determine which ones are expired.
                cutoff = date.today() - timedelta(days=self._retention_audit_days)
                expired: list[str] = []
                for name in all_partitions:
                    m = re.match(r"^audit_logs_(\d{4})_(\d{2})$", name)
                    if not m:
                        continue
                    year, month = int(m.group(1)), int(m.group(2))
                    if month == 12:
                        end_year, end_month = year + 1, 1
                    else:
                        end_year, end_month = year, month + 1
                    partition_end = date(end_year, end_month, 1)
                    if partition_end <= cutoff:
                        expired.append(name)

                dropped_count: int = await conn.fetchval(
                    "SELECT drop_expired_audit_partitions($1)",
                    self._retention_audit_days,
                )

            logger.info(
                "retention.partitions.dropped",
                count=dropped_count,
                expired_names=expired,
            )
            return expired

        except Exception as exc:
            logger.warning(
                "retention.partitions.drop_failed",
                error=str(exc),
            )
            return []

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _write_audit_record(self, result: PurgeResult) -> None:
        """Write an audit record for a purge execution (best-effort)."""
        if self._audit_service is None:
            return
        try:
            await self._audit_service.log_event(
                actor_id=None,
                actor_role="system",
                action="data_retention.purge",
                resource_type=result.category,
                after_state={
                    "category": result.category,
                    "records_affected": result.records_affected,
                    "duration_ms": round(result.duration_ms, 1),
                    "status": result.status,
                    "error_message": result.error_message,
                    "partitions_dropped": result.partitions_dropped,
                },
            )
        except Exception as exc:
            logger.critical(
                "retention.audit_write.failed",
                category=result.category,
                error=str(exc),
            )
