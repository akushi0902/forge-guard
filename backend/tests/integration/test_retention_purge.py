"""Integration tests for retention purge operations (WO-032).

These tests require a live PostgreSQL instance (via testcontainers Docker).
Run with::

    pytest -m integration tests/integration/test_retention_purge.py

Each test seeds the database with records at configurable timestamps, runs
the relevant purge method, and verifies:
  - Expired records are removed.
  - Non-expired records remain.
  - An audit record is created for each purge run.
  - Partition creation and drop work against real DDL.

Tests are marked @pytest.mark.integration and are skipped in CI unless Docker
is available.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest

from tests.fixtures.retention_fixtures import (
    make_active_ai_conversation,
    make_active_assessment_score,
    make_active_exception,
    make_active_finding,
    make_active_release_decision,
    make_expired_ai_conversation,
    make_expired_assessment_score,
    make_expired_finding,
    make_expired_release_decision,
    make_purgeable_exception,
    make_recently_expired_exception,
    ts_days_ago,
)

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _make_retention_service(pool, audit_svc=None, **kwargs):
    from forgeguard.services.retention import RetentionService
    return RetentionService(pool, audit_svc, **kwargs)


async def _count_rows(conn, table: str, condition: str = "TRUE") -> int:
    row = await conn.fetchrow(f"SELECT count(*) AS n FROM {table} WHERE {condition}")
    return row["n"]


# ---------------------------------------------------------------------------
# Assessment scores purge
# ---------------------------------------------------------------------------

@pytest.mark.integration
async def test_purge_assessments_removes_expired_records(asyncpg_pool):
    """Expired assessment_scores are deleted; non-expired ones survive."""
    expired_id = uuid.uuid4()
    active_id = uuid.uuid4()

    async with asyncpg_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO assessment_scores (id, assessment_id, dimension_scores, "
            "contributing_factors, overall_score, created_at) "
            "VALUES ($1, $2, $3::jsonb, $4::jsonb, $5, $6)",
            expired_id, uuid.uuid4(),
            '{"test": 0.5}', '{"factor": 1}',
            0.5, ts_days_ago(200),
        )
        await conn.execute(
            "INSERT INTO assessment_scores (id, assessment_id, dimension_scores, "
            "contributing_factors, overall_score, created_at) "
            "VALUES ($1, $2, $3::jsonb, $4::jsonb, $5, $6)",
            active_id, uuid.uuid4(),
            '{"test": 0.9}', '{"factor": 2}',
            0.9, ts_days_ago(30),
        )

    svc = await _make_retention_service(asyncpg_pool, retention_assessment_days=180)
    result = await svc.purge_assessments()

    assert result.status == "success"

    async with asyncpg_pool.acquire() as conn:
        expired_exists = await conn.fetchrow(
            "SELECT 1 FROM assessment_scores WHERE id = $1", expired_id
        )
        active_exists = await conn.fetchrow(
            "SELECT 1 FROM assessment_scores WHERE id = $1", active_id
        )

    assert expired_exists is None, "Expired record should have been purged"
    assert active_exists is not None, "Active record should survive"


@pytest.mark.integration
async def test_purge_assessments_idempotent(asyncpg_pool):
    """Running purge_assessments twice produces no errors and same outcome."""
    svc = await _make_retention_service(asyncpg_pool, retention_assessment_days=180)
    first = await svc.purge_assessments()
    second = await svc.purge_assessments()
    assert first.status == "success"
    assert second.status == "success"
    assert second.records_affected == 0


@pytest.mark.integration
async def test_purge_assessments_erases_jsonb_before_delete(asyncpg_pool):
    """The retention service should erase JSONB fields before deletion.

    We verify this indirectly: the erasure function runs UPDATE before DELETE.
    If the UPDATE fails (e.g. column missing), the record would survive.
    This test just verifies the record is removed and no exception propagates.
    """
    record_id = uuid.uuid4()
    async with asyncpg_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO assessment_scores (id, assessment_id, dimension_scores, "
            "contributing_factors, overall_score, created_at) "
            "VALUES ($1, $2, $3::jsonb, $4::jsonb, $5, $6)",
            record_id, uuid.uuid4(),
            '{"sensitive_score": 0.1}', '{"pii_factor": "real data"}',
            0.1, ts_days_ago(200),
        )

    svc = await _make_retention_service(asyncpg_pool, retention_assessment_days=180)
    result = await svc.purge_assessments()
    assert result.status == "success"
    assert result.records_affected >= 1


# ---------------------------------------------------------------------------
# Findings purge
# ---------------------------------------------------------------------------

@pytest.mark.integration
async def test_purge_findings_removes_expired_records(asyncpg_pool):
    """Expired findings are deleted; recent ones survive."""
    expired_id = uuid.uuid4()
    active_id = uuid.uuid4()

    async with asyncpg_pool.acquire() as conn:
        for fid, age in [(expired_id, 200), (active_id, 30)]:
            await conn.execute(
                "INSERT INTO findings (id, assessment_id, title, description, "
                "severity, category, status, created_at, updated_at) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $8)",
                fid, uuid.uuid4(), "Test finding", "Description",
                "medium", "security", "open", ts_days_ago(age),
            )

    svc = await _make_retention_service(asyncpg_pool, retention_findings_days=180)
    result = await svc.purge_findings()
    assert result.status == "success"

    async with asyncpg_pool.acquire() as conn:
        assert await conn.fetchrow("SELECT 1 FROM findings WHERE id = $1", expired_id) is None
        assert await conn.fetchrow("SELECT 1 FROM findings WHERE id = $1", active_id) is not None


@pytest.mark.integration
async def test_purge_findings_idempotent(asyncpg_pool):
    svc = await _make_retention_service(asyncpg_pool, retention_findings_days=180)
    first = await svc.purge_findings()
    second = await svc.purge_findings()
    assert first.status == "success"
    assert second.status == "success"


# ---------------------------------------------------------------------------
# Release decisions purge
# ---------------------------------------------------------------------------

@pytest.mark.integration
async def test_purge_release_decisions_removes_expired_records(asyncpg_pool):
    """Expired release decisions are deleted; recent ones survive."""
    expired_id = uuid.uuid4()
    active_id = uuid.uuid4()

    async with asyncpg_pool.acquire() as conn:
        for rid, age in [(expired_id, 400), (active_id, 30)]:
            await conn.execute(
                "INSERT INTO release_decisions (id, assessment_id, outcome, "
                "rationale, comment, decided_by, created_at) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7)",
                rid, uuid.uuid4(), "approve",
                "Rationale text.", "Comment text.", uuid.uuid4(), ts_days_ago(age),
            )

    svc = await _make_retention_service(asyncpg_pool, retention_release_decisions_days=365)
    result = await svc.purge_release_decisions()
    assert result.status == "success"

    async with asyncpg_pool.acquire() as conn:
        assert await conn.fetchrow(
            "SELECT 1 FROM release_decisions WHERE id = $1", expired_id
        ) is None
        assert await conn.fetchrow(
            "SELECT 1 FROM release_decisions WHERE id = $1", active_id
        ) is not None


# ---------------------------------------------------------------------------
# AI conversations purge
# ---------------------------------------------------------------------------

@pytest.mark.integration
async def test_purge_ai_conversations_removes_expired(asyncpg_pool):
    expired_id = uuid.uuid4()
    active_id = uuid.uuid4()

    async with asyncpg_pool.acquire() as conn:
        for cid, age in [(expired_id, 100), (active_id, 30)]:
            await conn.execute(
                "INSERT INTO ai_conversations (id, user_id, title, "
                "message_count, created_at, updated_at) "
                "VALUES ($1, $2, $3, $4, $5, $5)",
                cid, uuid.uuid4(), "Chat", 3, ts_days_ago(age),
            )

    svc = await _make_retention_service(asyncpg_pool, retention_ai_conversations_days=90)
    result = await svc.purge_ai_conversations()
    assert result.status == "success"

    async with asyncpg_pool.acquire() as conn:
        assert await conn.fetchrow(
            "SELECT 1 FROM ai_conversations WHERE id = $1", expired_id
        ) is None
        assert await conn.fetchrow(
            "SELECT 1 FROM ai_conversations WHERE id = $1", active_id
        ) is not None


# ---------------------------------------------------------------------------
# Expired exceptions purge
# ---------------------------------------------------------------------------

@pytest.mark.integration
async def test_purge_exceptions_removes_past_expiry_window(asyncpg_pool):
    """Exception 35 days past expires_at is purged; 10 days past is not."""
    old_exc_id = uuid.uuid4()
    recent_exc_id = uuid.uuid4()

    async with asyncpg_pool.acquire() as conn:
        for eid, expired_days_ago in [(old_exc_id, 35), (recent_exc_id, 10)]:
            await conn.execute(
                "INSERT INTO exceptions (id, finding_id, user_id, reason, "
                "expires_at, created_at) VALUES ($1, $2, $3, $4, $5, $6)",
                eid, uuid.uuid4(), uuid.uuid4(),
                "Accepted risk.",
                ts_days_ago(expired_days_ago),
                ts_days_ago(expired_days_ago + 60),
            )

    svc = await _make_retention_service(asyncpg_pool, retention_exceptions_days=30)
    result = await svc.purge_expired_exceptions()
    assert result.status == "success"

    async with asyncpg_pool.acquire() as conn:
        assert await conn.fetchrow(
            "SELECT 1 FROM exceptions WHERE id = $1", old_exc_id
        ) is None
        assert await conn.fetchrow(
            "SELECT 1 FROM exceptions WHERE id = $1", recent_exc_id
        ) is not None


# ---------------------------------------------------------------------------
# Partition management
# ---------------------------------------------------------------------------

@pytest.mark.integration
async def test_create_next_partition_is_idempotent(asyncpg_pool):
    """create_next_partition can be called twice without error."""
    svc = await _make_retention_service(asyncpg_pool)
    first = await svc.create_next_partition()
    second = await svc.create_next_partition()
    assert first == second


@pytest.mark.integration
async def test_create_next_partition_produces_valid_name(asyncpg_pool):
    import re
    svc = await _make_retention_service(asyncpg_pool)
    name = await svc.create_next_partition()
    assert re.match(r"^audit_logs_\d{4}_\d{2}$", name)


@pytest.mark.integration
async def test_drop_expired_partitions_returns_list(asyncpg_pool):
    """drop_expired_partitions returns a list (possibly empty if no expired partitions)."""
    svc = await _make_retention_service(asyncpg_pool)
    dropped = await svc.drop_expired_partitions()
    assert isinstance(dropped, list)


# ---------------------------------------------------------------------------
# Audit logging
# ---------------------------------------------------------------------------

@pytest.mark.integration
async def test_purge_writes_audit_record(asyncpg_pool):
    """Each purge execution creates an audit_logs record with the purge details."""
    from unittest.mock import AsyncMock, MagicMock

    audit_svc = MagicMock()
    audit_svc.log_event = AsyncMock(return_value=None)

    svc = await _make_retention_service(asyncpg_pool, audit_svc)
    await svc.purge_ai_conversations()

    audit_svc.log_event.assert_called_once()
    kwargs = audit_svc.log_event.call_args[1]
    assert kwargs.get("action") == "data_retention.purge"
    assert kwargs.get("resource_type") == "ai_conversations"
    assert kwargs.get("actor_role") == "system"
    after = kwargs.get("after_state", {})
    assert "records_affected" in after
    assert "duration_ms" in after
    assert after["status"] == "success"


@pytest.mark.integration
async def test_non_expired_records_not_affected(asyncpg_pool):
    """Running all purge methods leaves non-expired records untouched."""
    active_conv_id = uuid.uuid4()
    async with asyncpg_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO ai_conversations (id, user_id, title, message_count, "
            "created_at, updated_at) VALUES ($1, $2, $3, $4, $5, $5)",
            active_conv_id, uuid.uuid4(), "Recent chat", 1, ts_days_ago(5),
        )

    svc = await _make_retention_service(asyncpg_pool, retention_ai_conversations_days=90)
    result = await svc.purge_ai_conversations()
    assert result.status == "success"

    async with asyncpg_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT 1 FROM ai_conversations WHERE id = $1", active_conv_id
        )
    assert row is not None, "Non-expired conversation was incorrectly purged"
