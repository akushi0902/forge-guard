"""Unit tests for RetentionService (WO-032).

Tests cover:
- PurgeResult dataclass fields and defaults
- Retention period calculations (cutoff date logic)
- Partition name generation in create_next_partition()
- Purge methods return PurgeResult with status="success" when no records exist
- Purge methods return PurgeResult with status="failure" on DB error
- Idempotency: calling purge twice on an empty set returns success both times
- Audit record is written via AuditService after each successful purge
- Audit record write failure does not propagate to the caller

All tests use mock asyncpg pools — no database required.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from forgeguard.services.retention import PurgeResult, RetentionService


# ---------------------------------------------------------------------------
# Mock pool helpers
# ---------------------------------------------------------------------------

def _make_conn(
    fetchval_return=None,
    fetch_return=None,
) -> AsyncMock:
    """Return a mock asyncpg connection."""
    conn = AsyncMock()
    conn.fetchval = AsyncMock(return_value=fetchval_return)
    conn.fetch = AsyncMock(return_value=fetch_return or [])
    conn.execute = AsyncMock(return_value=None)
    # transaction() is an async context manager that yields None
    txn_ctx = MagicMock()
    txn_ctx.__aenter__ = AsyncMock(return_value=None)
    txn_ctx.__aexit__ = AsyncMock(return_value=False)
    conn.transaction = MagicMock(return_value=txn_ctx)
    return conn


def _make_pool(conn: AsyncMock | None = None) -> MagicMock:
    """Return a mock asyncpg pool whose acquire() yields conn."""
    if conn is None:
        conn = _make_conn()
    pool = MagicMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=False)
    pool.acquire = MagicMock(return_value=ctx)
    return pool


def _make_cutoff_conn(cutoff: datetime | None = None) -> AsyncMock:
    """Connection that returns a cutoff datetime from fetchval, then 0 rows."""
    if cutoff is None:
        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=180)
    conn = _make_conn()
    # First fetchval call returns cutoff; subsequent calls return 0
    conn.fetchval = AsyncMock(side_effect=[cutoff, 0])
    return conn


# ---------------------------------------------------------------------------
# PurgeResult dataclass
# ---------------------------------------------------------------------------

class TestPurgeResult:

    def test_required_fields(self):
        r = PurgeResult(
            category="audit_logs",
            records_affected=5,
            duration_ms=123.4,
            status="success",
        )
        assert r.category == "audit_logs"
        assert r.records_affected == 5
        assert r.duration_ms == 123.4
        assert r.status == "success"

    def test_optional_error_message_defaults_to_none(self):
        r = PurgeResult(category="findings", records_affected=0, duration_ms=1.0, status="success")
        assert r.error_message is None

    def test_optional_list_fields_default_to_empty(self):
        r = PurgeResult(category="audit_logs", records_affected=0, duration_ms=1.0, status="success")
        assert r.partitions_dropped == []
        assert r.partitions_created == []

    def test_failure_status_with_message(self):
        r = PurgeResult(
            category="ai_conversations",
            records_affected=0,
            duration_ms=50.0,
            status="failure",
            error_message="connection refused",
        )
        assert r.status == "failure"
        assert r.error_message == "connection refused"


# ---------------------------------------------------------------------------
# RetentionService constructor
# ---------------------------------------------------------------------------

class TestRetentionServiceInit:

    def test_default_retention_periods(self):
        pool = _make_pool()
        svc = RetentionService(pool)
        assert svc._retention_audit_days == 365
        assert svc._retention_assessment_days == 180
        assert svc._retention_findings_days == 180
        assert svc._retention_release_decisions_days == 365
        assert svc._retention_ai_conversations_days == 90
        assert svc._retention_exceptions_days == 30

    def test_custom_retention_periods(self):
        pool = _make_pool()
        svc = RetentionService(
            pool,
            retention_audit_days=730,
            retention_assessment_days=90,
            retention_findings_days=90,
            retention_release_decisions_days=730,
            retention_ai_conversations_days=45,
            retention_exceptions_days=7,
        )
        assert svc._retention_audit_days == 730
        assert svc._retention_assessment_days == 90
        assert svc._retention_ai_conversations_days == 45
        assert svc._retention_exceptions_days == 7

    def test_audit_service_is_optional(self):
        pool = _make_pool()
        svc = RetentionService(pool)
        assert svc._audit_service is None


# ---------------------------------------------------------------------------
# purge_audit_logs
# ---------------------------------------------------------------------------

class TestPurgeAuditLogs:

    @pytest.mark.asyncio
    async def test_success_when_db_returns_zero_dropped(self):
        conn = _make_conn(fetchval_return=0)
        pool = _make_pool(conn)
        svc = RetentionService(pool)
        result = await svc.purge_audit_logs()
        assert result.status == "success"
        assert result.category == "audit_logs"
        assert result.records_affected == 0

    @pytest.mark.asyncio
    async def test_success_with_partitions_dropped(self):
        conn = _make_conn(fetchval_return=3)
        pool = _make_pool(conn)
        svc = RetentionService(pool)
        result = await svc.purge_audit_logs()
        assert result.status == "success"
        assert result.records_affected == 3

    @pytest.mark.asyncio
    async def test_failure_on_db_error(self):
        pool = MagicMock()
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(side_effect=RuntimeError("DB unavailable"))
        ctx.__aexit__ = AsyncMock(return_value=False)
        pool.acquire = MagicMock(return_value=ctx)
        svc = RetentionService(pool)
        result = await svc.purge_audit_logs()
        assert result.status == "failure"
        assert "DB unavailable" in (result.error_message or "")

    @pytest.mark.asyncio
    async def test_calls_drop_expired_audit_partitions(self):
        conn = _make_conn(fetchval_return=2)
        pool = _make_pool(conn)
        svc = RetentionService(pool, retention_audit_days=180)
        await svc.purge_audit_logs()
        # fetchval should have been called with the SQL and retention_days arg
        conn.fetchval.assert_called_once()
        call_args = conn.fetchval.call_args
        assert "drop_expired_audit_partitions" in call_args[0][0]
        assert call_args[0][1] == 180

    @pytest.mark.asyncio
    async def test_audit_service_called_on_success(self):
        conn = _make_conn(fetchval_return=1)
        pool = _make_pool(conn)
        audit_svc = MagicMock()
        audit_svc.log_event = AsyncMock(return_value=None)
        svc = RetentionService(pool, audit_svc)
        await svc.purge_audit_logs()
        audit_svc.log_event.assert_called_once()
        kwargs = audit_svc.log_event.call_args[1]
        assert kwargs["action"] == "data_retention.purge"
        assert kwargs["resource_type"] == "audit_logs"


# ---------------------------------------------------------------------------
# purge_assessments
# ---------------------------------------------------------------------------

class TestPurgeAssessments:

    @pytest.mark.asyncio
    async def test_success_with_no_expired_records(self):
        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=180)
        conn = _make_conn()
        # First call returns cutoff; second (in the loop) returns 0 rows
        conn.fetchval = AsyncMock(return_value=cutoff)
        conn.fetch = AsyncMock(return_value=[])  # no rows
        pool = _make_pool(conn)
        svc = RetentionService(pool)
        result = await svc.purge_assessments()
        assert result.status == "success"
        assert result.category == "assessment_scores"
        assert result.records_affected == 0

    @pytest.mark.asyncio
    async def test_failure_on_db_error(self):
        pool = MagicMock()
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(side_effect=RuntimeError("timeout"))
        ctx.__aexit__ = AsyncMock(return_value=False)
        pool.acquire = MagicMock(return_value=ctx)
        svc = RetentionService(pool)
        result = await svc.purge_assessments()
        assert result.status == "failure"

    @pytest.mark.asyncio
    async def test_idempotent_second_call_returns_success(self):
        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=180)
        conn = _make_conn()
        conn.fetchval = AsyncMock(return_value=cutoff)
        conn.fetch = AsyncMock(return_value=[])
        pool = _make_pool(conn)
        svc = RetentionService(pool)
        first = await svc.purge_assessments()
        second = await svc.purge_assessments()
        assert first.status == "success"
        assert second.status == "success"


# ---------------------------------------------------------------------------
# purge_findings
# ---------------------------------------------------------------------------

class TestPurgeFindings:

    @pytest.mark.asyncio
    async def test_success_with_no_expired_records(self):
        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=180)
        conn = _make_conn()
        conn.fetchval = AsyncMock(side_effect=[cutoff, 0])
        pool = _make_pool(conn)
        svc = RetentionService(pool)
        result = await svc.purge_findings()
        assert result.status == "success"
        assert result.category == "findings"

    @pytest.mark.asyncio
    async def test_failure_on_db_error(self):
        pool = MagicMock()
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(side_effect=Exception("network error"))
        ctx.__aexit__ = AsyncMock(return_value=False)
        pool.acquire = MagicMock(return_value=ctx)
        svc = RetentionService(pool)
        result = await svc.purge_findings()
        assert result.status == "failure"


# ---------------------------------------------------------------------------
# purge_release_decisions
# ---------------------------------------------------------------------------

class TestPurgeReleaseDecisions:

    @pytest.mark.asyncio
    async def test_success_with_no_expired_records(self):
        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=365)
        conn = _make_conn()
        conn.fetchval = AsyncMock(return_value=cutoff)
        conn.fetch = AsyncMock(return_value=[])
        pool = _make_pool(conn)
        svc = RetentionService(pool)
        result = await svc.purge_release_decisions()
        assert result.status == "success"
        assert result.category == "release_decisions"

    @pytest.mark.asyncio
    async def test_failure_on_db_error(self):
        pool = MagicMock()
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(side_effect=RuntimeError("connection dropped"))
        ctx.__aexit__ = AsyncMock(return_value=False)
        pool.acquire = MagicMock(return_value=ctx)
        svc = RetentionService(pool)
        result = await svc.purge_release_decisions()
        assert result.status == "failure"


# ---------------------------------------------------------------------------
# purge_ai_conversations
# ---------------------------------------------------------------------------

class TestPurgeAiConversations:

    @pytest.mark.asyncio
    async def test_success_with_no_expired_records(self):
        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=90)
        conn = _make_conn()
        conn.fetchval = AsyncMock(side_effect=[cutoff, 0])
        pool = _make_pool(conn)
        svc = RetentionService(pool)
        result = await svc.purge_ai_conversations()
        assert result.status == "success"
        assert result.category == "ai_conversations"


# ---------------------------------------------------------------------------
# purge_expired_exceptions
# ---------------------------------------------------------------------------

class TestPurgeExpiredExceptions:

    @pytest.mark.asyncio
    async def test_success_with_no_purgeable_exceptions(self):
        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=30)
        conn = _make_conn()
        conn.fetchval = AsyncMock(side_effect=[cutoff, 0])
        pool = _make_pool(conn)
        svc = RetentionService(pool)
        result = await svc.purge_expired_exceptions()
        assert result.status == "success"
        assert result.category == "exceptions"


# ---------------------------------------------------------------------------
# create_next_partition
# ---------------------------------------------------------------------------

class TestCreateNextPartition:

    @pytest.mark.asyncio
    async def test_returns_partition_name_string(self):
        conn = _make_conn()
        pool = _make_pool(conn)
        svc = RetentionService(pool)
        name = await svc.create_next_partition()
        assert isinstance(name, str)
        assert name.startswith("audit_logs_")

    @pytest.mark.asyncio
    async def test_partition_name_format(self):
        """Partition name must match audit_logs_YYYY_MM."""
        import re
        conn = _make_conn()
        pool = _make_pool(conn)
        svc = RetentionService(pool)
        name = await svc.create_next_partition()
        assert re.match(r"^audit_logs_\d{4}_\d{2}$", name), f"Bad name: {name}"

    @pytest.mark.asyncio
    async def test_calls_create_audit_partition_function(self):
        conn = _make_conn()
        pool = _make_pool(conn)
        svc = RetentionService(pool)
        await svc.create_next_partition()
        conn.execute.assert_called_once()
        sql = conn.execute.call_args[0][0]
        assert "create_audit_partition" in sql

    @pytest.mark.asyncio
    async def test_db_error_is_caught_and_logged(self):
        """DDL failure should not raise — it logs a warning and returns the name."""
        conn = _make_conn()
        conn.execute = AsyncMock(side_effect=RuntimeError("partition already exists"))
        pool = _make_pool(conn)
        svc = RetentionService(pool)
        name = await svc.create_next_partition()
        assert isinstance(name, str)

    @pytest.mark.asyncio
    async def test_december_rolls_over_to_january(self):
        """December next month should be January of the following year."""
        import re
        from datetime import date
        conn = _make_conn()
        pool = _make_pool(conn)
        svc = RetentionService(pool)
        with patch("forgeguard.services.retention.date") as mock_date:
            mock_date.today.return_value = date(2026, 12, 15)
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
            name = await svc.create_next_partition()
        assert "2027_01" in name


# ---------------------------------------------------------------------------
# _write_audit_record (best-effort)
# ---------------------------------------------------------------------------

class TestWriteAuditRecord:

    @pytest.mark.asyncio
    async def test_no_audit_service_is_noop(self):
        pool = _make_pool()
        svc = RetentionService(pool, audit_service=None)
        result = PurgeResult(category="audit_logs", records_affected=0, duration_ms=1.0, status="success")
        # Should not raise
        await svc._write_audit_record(result)

    @pytest.mark.asyncio
    async def test_audit_service_failure_does_not_propagate(self):
        pool = _make_pool()
        audit_svc = MagicMock()
        audit_svc.log_event = AsyncMock(side_effect=RuntimeError("audit DB down"))
        svc = RetentionService(pool, audit_svc)
        result = PurgeResult(category="audit_logs", records_affected=0, duration_ms=1.0, status="success")
        # Must not raise
        await svc._write_audit_record(result)

    @pytest.mark.asyncio
    async def test_audit_record_contains_required_fields(self):
        pool = _make_pool()
        audit_svc = MagicMock()
        audit_svc.log_event = AsyncMock(return_value=None)
        svc = RetentionService(pool, audit_svc)
        result = PurgeResult(
            category="findings",
            records_affected=42,
            duration_ms=350.5,
            status="success",
        )
        await svc._write_audit_record(result)
        audit_svc.log_event.assert_called_once()
        kwargs = audit_svc.log_event.call_args[1]
        after = kwargs["after_state"]
        assert after["category"] == "findings"
        assert after["records_affected"] == 42
        assert after["status"] == "success"
        assert "duration_ms" in after
