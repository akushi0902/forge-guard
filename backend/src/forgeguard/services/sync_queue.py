"""Database-backed retry queue for Forge Scorecard score publishing (WO-090).

Uses the pending_sync_jobs table with SELECT FOR UPDATE SKIP LOCKED for
concurrent-safe job processing that survives process restarts.

Exponential backoff delays (seconds): 2, 4, 8, 16, 32 (max 5 retries).
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import asyncpg
import structlog

logger = structlog.get_logger(__name__)

# Backoff delays indexed by retry_count (0-based, i.e. delay after attempt N).
_BACKOFF_SECONDS: list[int] = [2, 4, 8, 16, 32]
_DEFAULT_MAX_RETRIES: int = 5
_JOB_TYPE_SCORECARD_PUBLISH: str = "scorecard_publish"


def _backoff_delay(retry_count: int) -> int:
    """Return the seconds to wait before the next retry attempt."""
    idx = min(retry_count, len(_BACKOFF_SECONDS) - 1)
    return _BACKOFF_SECONDS[idx]


class SyncQueueService:
    """Manages the pending_sync_jobs retry queue.

    Args:
        pool: asyncpg connection pool.
    """

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    # ------------------------------------------------------------------
    # Enqueueing
    # ------------------------------------------------------------------

    async def enqueue_job(
        self,
        *,
        job_type: str = _JOB_TYPE_SCORECARD_PUBLISH,
        payload: dict[str, Any],
        max_retries: int = _DEFAULT_MAX_RETRIES,
    ) -> dict[str, Any]:
        """Insert a new sync job into the queue.

        The job is scheduled for immediate processing (next_retry_at = now).

        Returns the inserted row as a dict.
        """
        job_id = uuid.uuid4()
        now = datetime.now(tz=timezone.utc)
        q = """
            INSERT INTO pending_sync_jobs
                (id, job_type, payload, status, retry_count, max_retries,
                 next_retry_at, created_at, updated_at)
            VALUES ($1, $2, $3, 'pending', 0, $4, $5, $6, $6)
            RETURNING *
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                q,
                job_id,
                job_type,
                json.dumps(payload),
                max_retries,
                now,
                now,
            )
        result = dict(row)
        logger.info(
            "sync_queue.job_enqueued",
            job_id=str(job_id),
            job_type=job_type,
        )
        return result

    # ------------------------------------------------------------------
    # Processing
    # ------------------------------------------------------------------

    async def process_pending_jobs(
        self,
        handler: Any,  # callable: async (payload) -> dict[str, Any]
        *,
        batch_size: int = 10,
    ) -> int:
        """Process due pending jobs with SELECT FOR UPDATE SKIP LOCKED.

        Args:
            handler:    Async callable receiving the payload dict and
                        returning a result dict with keys:
                        success (bool), retryable (bool), error (str|None).
            batch_size: Maximum jobs to process per call.

        Returns:
            Number of jobs processed (attempted).
        """
        now = datetime.now(tz=timezone.utc)
        processed = 0

        select_q = """
            SELECT id, job_type, payload, retry_count, max_retries
            FROM pending_sync_jobs
            WHERE status = 'pending'
              AND (next_retry_at IS NULL OR next_retry_at <= $1)
            ORDER BY next_retry_at ASC NULLS FIRST
            LIMIT $2
            FOR UPDATE SKIP LOCKED
        """

        async with self._pool.acquire() as conn:
            async with conn.transaction():
                rows = await conn.fetch(select_q, now, batch_size)
                for row in rows:
                    job_id = row["id"]
                    retry_count = row["retry_count"]
                    max_retries = row["max_retries"]
                    try:
                        payload = json.loads(row["payload"]) if isinstance(row["payload"], str) else row["payload"]
                    except (json.JSONDecodeError, TypeError):
                        payload = {}

                    log = logger.bind(job_id=str(job_id), retry_count=retry_count)
                    log.info("sync_queue.job_processing")

                    try:
                        result = await handler(payload)
                        success = result.get("success", False)
                        retryable = result.get("retryable", False)
                        error_msg = result.get("error")
                    except Exception as exc:
                        success = False
                        retryable = True
                        error_msg = str(exc)
                        log.error("sync_queue.handler_exception", error=error_msg)

                    if success:
                        await self._mark_completed(conn, job_id)
                        log.info("sync_queue.job_completed")
                    elif not retryable or retry_count >= max_retries - 1:
                        await self._mark_failed(conn, job_id, error=error_msg, exhausted=retry_count >= max_retries - 1)
                        if retry_count >= max_retries - 1:
                            log.error("sync_queue.job_retries_exhausted")
                        else:
                            log.error("sync_queue.job_failed_no_retry", error=error_msg)
                    else:
                        next_delay = _backoff_delay(retry_count)
                        next_retry = now + timedelta(seconds=next_delay)
                        await self._reschedule(conn, job_id, retry_count + 1, next_retry, error_msg)
                        log.info("sync_queue.job_rescheduled", next_retry=next_retry.isoformat(), delay_seconds=next_delay)

                    processed += 1

        return processed

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------

    async def _mark_completed(self, conn: asyncpg.Connection, job_id: uuid.UUID) -> None:
        await conn.execute(
            "UPDATE pending_sync_jobs SET status='completed', updated_at=$1 WHERE id=$2",
            datetime.now(tz=timezone.utc),
            job_id,
        )

    async def _mark_failed(
        self,
        conn: asyncpg.Connection,
        job_id: uuid.UUID,
        *,
        error: Optional[str],
        exhausted: bool,
    ) -> None:
        status = "stale" if exhausted else "failed"
        await conn.execute(
            """UPDATE pending_sync_jobs
               SET status=$1, last_error=$2, updated_at=$3
               WHERE id=$4""",
            status,
            error,
            datetime.now(tz=timezone.utc),
            job_id,
        )

    async def _reschedule(
        self,
        conn: asyncpg.Connection,
        job_id: uuid.UUID,
        new_retry_count: int,
        next_retry_at: datetime,
        last_error: Optional[str],
    ) -> None:
        await conn.execute(
            """UPDATE pending_sync_jobs
               SET retry_count=$1, next_retry_at=$2, last_error=$3, updated_at=$4
               WHERE id=$5""",
            new_retry_count,
            next_retry_at,
            last_error,
            datetime.now(tz=timezone.utc),
            job_id,
        )

    # ------------------------------------------------------------------
    # Public mark helpers (used by orchestrator for direct updates)
    # ------------------------------------------------------------------

    async def mark_completed(self, job_id: uuid.UUID) -> None:
        async with self._pool.acquire() as conn:
            await self._mark_completed(conn, job_id)

    async def mark_failed(self, job_id: uuid.UUID, *, error: Optional[str] = None) -> None:
        async with self._pool.acquire() as conn:
            await self._mark_failed(conn, job_id, error=error, exhausted=False)
