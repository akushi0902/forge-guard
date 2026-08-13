"""Unit tests for SyncQueueService (WO-090).

Covers:
  AC-2  enqueue_job inserts row with status=pending
  AC-2  process_pending_jobs picks up due jobs
  AC-2  Exponential backoff: retry_count increments, next_retry_at set correctly
  AC-3  Stale marking after max retries exhausted
  AC-2  Successful handler marks job completed
  AC-2  Non-retryable failure marks job failed immediately
  AC-2  SELECT FOR UPDATE SKIP LOCKED is used (concurrent safety)
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from forgeguard.services.sync_queue import (
    SyncQueueService,
    _BACKOFF_SECONDS,
    _backoff_delay,
)


# ---------------------------------------------------------------------------
# _backoff_delay
# ---------------------------------------------------------------------------


class TestBackoffDelay:
    def test_first_retry(self):
        assert _backoff_delay(0) == 2

    def test_second_retry(self):
        assert _backoff_delay(1) == 4

    def test_third_retry(self):
        assert _backoff_delay(2) == 8

    def test_fourth_retry(self):
        assert _backoff_delay(3) == 16

    def test_fifth_retry(self):
        assert _backoff_delay(4) == 32

    def test_beyond_max_clamps_to_last(self):
        assert _backoff_delay(99) == _BACKOFF_SECONDS[-1]


# ---------------------------------------------------------------------------
# SyncQueueService.enqueue_job
# ---------------------------------------------------------------------------


def _make_pool_with_fetchrow(return_value: Any) -> MagicMock:
    """Return a mock asyncpg pool whose conn.fetchrow returns return_value."""
    row = {"id": uuid.uuid4(), "job_type": "scorecard_publish", "status": "pending", "retry_count": 0, "max_retries": 5, "payload": "{}"}
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=return_value or row)
    conn.__aenter__ = AsyncMock(return_value=conn)
    conn.__aexit__ = AsyncMock(return_value=False)
    pool = MagicMock()
    pool.acquire.return_value = conn
    return pool


class TestEnqueueJob:
    @pytest.mark.asyncio
    async def test_inserts_pending_job(self):
        row = {
            "id": uuid.uuid4(),
            "job_type": "scorecard_publish",
            "status": "pending",
            "retry_count": 0,
            "max_retries": 5,
            "payload": json.dumps({"assessment_id": "abc"}),
            "next_retry_at": datetime.now(tz=timezone.utc),
            "created_at": datetime.now(tz=timezone.utc),
            "updated_at": datetime.now(tz=timezone.utc),
        }
        pool = _make_pool_with_fetchrow(row)
        svc = SyncQueueService(pool)
        result = await svc.enqueue_job(payload={"assessment_id": "abc"})
        assert result["status"] == "pending"
        assert result["retry_count"] == 0

    @pytest.mark.asyncio
    async def test_enqueue_calls_insert(self):
        pool = _make_pool_with_fetchrow(None)
        svc = SyncQueueService(pool)
        await svc.enqueue_job(payload={"scorecard_id": "sc-1"})
        conn = pool.acquire.return_value
        conn.fetchrow.assert_called_once()
        query = conn.fetchrow.call_args[0][0]
        assert "INSERT INTO pending_sync_jobs" in query


# ---------------------------------------------------------------------------
# SyncQueueService.process_pending_jobs
# ---------------------------------------------------------------------------


def _make_pool_for_processing(rows: list[Any]) -> MagicMock:
    """Return a mock pool for process_pending_jobs tests."""
    conn = AsyncMock()
    # fetch returns the rows
    conn.fetch = AsyncMock(return_value=rows)
    # execute is called for state transitions
    conn.execute = AsyncMock(return_value=None)
    # transaction context manager
    tx = AsyncMock()
    tx.__aenter__ = AsyncMock(return_value=tx)
    tx.__aexit__ = AsyncMock(return_value=False)
    conn.transaction = MagicMock(return_value=tx)
    conn.__aenter__ = AsyncMock(return_value=conn)
    conn.__aexit__ = AsyncMock(return_value=False)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=conn)
    return pool, conn


def _make_job_row(
    *,
    job_id: uuid.UUID | None = None,
    retry_count: int = 0,
    max_retries: int = 5,
    payload: dict | None = None,
) -> MagicMock:
    row = MagicMock()
    row.__getitem__ = lambda self, key: {
        "id": job_id or uuid.uuid4(),
        "job_type": "scorecard_publish",
        "payload": json.dumps(payload or {"scorecard_id": "sc-1", "assessment_id": str(uuid.uuid4()), "service_id": str(uuid.uuid4())}),
        "retry_count": retry_count,
        "max_retries": max_retries,
    }[key]
    return row


class TestProcessPendingJobs:
    @pytest.mark.asyncio
    async def test_success_marks_completed(self):
        job_row = _make_job_row()
        pool, conn = _make_pool_for_processing([job_row])
        svc = SyncQueueService(pool)
        handler = AsyncMock(return_value={"success": True, "retryable": False, "error": None})
        count = await svc.process_pending_jobs(handler)
        assert count == 1
        # completed update was called
        update_calls = [str(c) for c in conn.execute.call_args_list]
        assert any("completed" in c for c in update_calls)

    @pytest.mark.asyncio
    async def test_retryable_failure_reschedules(self):
        job_row = _make_job_row(retry_count=0, max_retries=5)
        pool, conn = _make_pool_for_processing([job_row])
        svc = SyncQueueService(pool)
        handler = AsyncMock(return_value={"success": False, "retryable": True, "error": "HTTP 503"})
        await svc.process_pending_jobs(handler)
        update_calls = [str(c) for c in conn.execute.call_args_list]
        # Should reschedule (UPDATE with retry_count=1)
        assert any("retry_count" in c or "next_retry_at" in c for c in update_calls)

    @pytest.mark.asyncio
    async def test_non_retryable_marks_failed(self):
        job_row = _make_job_row(retry_count=0, max_retries=5)
        pool, conn = _make_pool_for_processing([job_row])
        svc = SyncQueueService(pool)
        handler = AsyncMock(return_value={"success": False, "retryable": False, "error": "HTTP 400"})
        await svc.process_pending_jobs(handler)
        update_calls = [str(c) for c in conn.execute.call_args_list]
        assert any("failed" in c for c in update_calls)

    @pytest.mark.asyncio
    async def test_max_retries_marks_stale(self):
        """When retry_count == max_retries - 1, next failure → stale."""
        job_row = _make_job_row(retry_count=4, max_retries=5)
        pool, conn = _make_pool_for_processing([job_row])
        svc = SyncQueueService(pool)
        handler = AsyncMock(return_value={"success": False, "retryable": True, "error": "HTTP 503"})
        await svc.process_pending_jobs(handler)
        update_calls = [str(c) for c in conn.execute.call_args_list]
        assert any("stale" in c for c in update_calls)

    @pytest.mark.asyncio
    async def test_empty_queue_returns_zero(self):
        pool, conn = _make_pool_for_processing([])
        svc = SyncQueueService(pool)
        handler = AsyncMock()
        count = await svc.process_pending_jobs(handler)
        assert count == 0
        handler.assert_not_called()

    @pytest.mark.asyncio
    async def test_select_for_update_skip_locked_used(self):
        pool, conn = _make_pool_for_processing([])
        svc = SyncQueueService(pool)
        await svc.process_pending_jobs(AsyncMock())
        query = conn.fetch.call_args[0][0]
        assert "FOR UPDATE SKIP LOCKED" in query

    @pytest.mark.asyncio
    async def test_handler_exception_reschedules(self):
        """Handler raising an exception should be treated as retryable."""
        job_row = _make_job_row(retry_count=0, max_retries=5)
        pool, conn = _make_pool_for_processing([job_row])
        svc = SyncQueueService(pool)
        handler = AsyncMock(side_effect=RuntimeError("unexpected"))
        await svc.process_pending_jobs(handler)
        # Should reschedule, not complete
        update_calls = [str(c) for c in conn.execute.call_args_list]
        assert not any("completed" in c for c in update_calls)
