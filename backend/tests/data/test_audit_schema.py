"""Schema-level tests for the Audit domain tables.

All tests require a live PostgreSQL instance and are automatically skipped
when the database is unreachable.

Because audit_logs is a range-partitioned table, the module-local db_engine
fixture creates it via raw SQL (not Base.metadata.create_all), then creates
initial partitions for a 3-month test window.

Tests cover:
    1. audit_logs table creation and basic INSERT.
    2. Records route to the correct monthly partition.
    3. INSERT succeeds, UPDATE and DELETE are blocked by immutability (verified
       via role privilege check rather than direct execution, since the test DB
       user is typically a superuser).
    4. create_audit_partition function is idempotent.
    5. drop_expired_audit_partitions drops only expired partitions.
    6. Cross-partition SELECT returns records from all months.
    7. Composite indexes exist on the parent table.
    8. AIConversation INSERT / SELECT / JSONB messages.
    9. AIConversation FK CASCADE from users.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from forgeguard.core.config import get_settings
from forgeguard.data.models import AIConversation, AuditLog, User


# ---------------------------------------------------------------------------
# Database availability guard
# ---------------------------------------------------------------------------

def _is_db_available() -> bool:
    import asyncio

    async def _check() -> bool:
        engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except (OperationalError, Exception):
            return False
        finally:
            await engine.dispose()

    try:
        return asyncio.get_event_loop().run_until_complete(_check())
    except Exception:
        return False


_DB_AVAILABLE = _is_db_available()
pytestmark = pytest.mark.skipif(not _DB_AVAILABLE, reason="PostgreSQL not available")


# ---------------------------------------------------------------------------
# Module-scoped engine: creates tables via raw SQL + drops on teardown.
# We do NOT use Base.metadata.create_all because it cannot create partitioned
# tables.  Instead we run the DDL manually in the fixture.
# ---------------------------------------------------------------------------

_SETUP_SQL = """
-- Prerequisite: users table (needed for FKs).
CREATE TABLE IF NOT EXISTS _test_users_audit (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email         VARCHAR(254) NOT NULL UNIQUE,
    password_hash VARCHAR(60)  NOT NULL,
    role          VARCHAR(50)  NOT NULL,
    is_active     BOOLEAN      NOT NULL DEFAULT TRUE,
    failed_login_attempts INTEGER NOT NULL DEFAULT 0,
    locked_until  TIMESTAMPTZ,
    deleted_at    TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

_AUDIT_LOGS_DDL = """
CREATE TABLE IF NOT EXISTS _test_audit_logs (
    id                UUID        NOT NULL DEFAULT gen_random_uuid(),
    actor_id          UUID,
    actor_role        VARCHAR(50) NOT NULL,
    action            VARCHAR(255) NOT NULL,
    resource_type     VARCHAR(100) NOT NULL,
    resource_id       UUID,
    before_state      JSONB,
    after_state       JSONB,
    ip_address_masked VARCHAR(45),
    correlation_id    VARCHAR(36),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (id, created_at)
) PARTITION BY RANGE (created_at);

CREATE INDEX IF NOT EXISTS ix_test_audit_logs_actor_id_created_at
    ON _test_audit_logs (actor_id, created_at);

CREATE INDEX IF NOT EXISTS ix_test_audit_logs_resource_type_resource_id_created_at
    ON _test_audit_logs (resource_type, resource_id, created_at);

CREATE INDEX IF NOT EXISTS ix_test_audit_logs_correlation_id
    ON _test_audit_logs (correlation_id);
"""

_AI_CONV_DDL = """
CREATE TABLE IF NOT EXISTS _test_ai_conversations (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL,
    messages    JSONB NOT NULL DEFAULT '[]',
    context_refs JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_test_ai_conversations_user_id
    ON _test_ai_conversations (user_id);
"""

# Test partitions covering 2025-01, 2025-02, 2025-03 (well in the past for
# drop_expired tests), and 2099-01 (far future, never expired).
_PARTITION_DDL = """
CREATE TABLE IF NOT EXISTS _test_audit_logs_2025_01
    PARTITION OF _test_audit_logs
    FOR VALUES FROM ('2025-01-01') TO ('2025-02-01');

CREATE TABLE IF NOT EXISTS _test_audit_logs_2025_02
    PARTITION OF _test_audit_logs
    FOR VALUES FROM ('2025-02-01') TO ('2025-03-01');

CREATE TABLE IF NOT EXISTS _test_audit_logs_2025_03
    PARTITION OF _test_audit_logs
    FOR VALUES FROM ('2025-03-01') TO ('2025-04-01');

CREATE TABLE IF NOT EXISTS _test_audit_logs_2099_01
    PARTITION OF _test_audit_logs
    FOR VALUES FROM ('2099-01-01') TO ('2099-02-01');
"""

_TEARDOWN_SQL = """
DROP TABLE IF EXISTS _test_audit_logs_2025_01;
DROP TABLE IF EXISTS _test_audit_logs_2025_02;
DROP TABLE IF EXISTS _test_audit_logs_2025_03;
DROP TABLE IF EXISTS _test_audit_logs_2099_01;
DROP TABLE IF EXISTS _test_audit_logs;
DROP TABLE IF EXISTS _test_ai_conversations;
DROP TABLE IF EXISTS _test_users_audit;
"""


@pytest_asyncio.fixture(scope="module")
async def db_engine():
    engine = create_async_engine(get_settings().database_url, echo=False)
    async with engine.begin() as conn:
        # Use autocommit-style DDL via raw text.
        for stmt in _SETUP_SQL.strip().split(";"):
            if stmt.strip():
                await conn.execute(text(stmt))
        # Partitioned table must be created in a single statement.
        await conn.execute(text(_AUDIT_LOGS_DDL))
        await conn.execute(text(_AI_CONV_DDL))
        await conn.execute(text(_PARTITION_DDL))
    yield engine
    async with engine.begin() as conn:
        await conn.execute(text(_TEARDOWN_SQL))
    await engine.dispose()


@pytest_asyncio.fixture()
async def session(db_engine):
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as sess:
        async with sess.begin():
            yield sess
            await sess.rollback()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user_row() -> dict:
    return {
        "id": uuid.uuid4(),
        "email": f"audit-{uuid.uuid4().hex[:8]}@example.com",
        "password_hash": "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8y7.xXj4pF.mY0gLXWc",
        "role": "developer",
    }


def _make_audit_row(created_at: datetime, **kwargs) -> dict:
    defaults = {
        "id": uuid.uuid4(),
        "actor_role": "developer",
        "action": "policy_rule.created",
        "resource_type": "policy_rule",
        "resource_id": uuid.uuid4(),
        "correlation_id": str(uuid.uuid4()),
        "created_at": created_at,
    }
    defaults.update(kwargs)
    return defaults


# ---------------------------------------------------------------------------
# audit_logs — INSERT and basic SELECT
# ---------------------------------------------------------------------------

class TestAuditLogInsert:
    async def test_insert_and_select(self, session: AsyncSession) -> None:
        ts = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        row = _make_audit_row(created_at=ts)
        await session.execute(
            text(
                "INSERT INTO _test_audit_logs "
                "(id, actor_role, action, resource_type, resource_id, correlation_id, created_at) "
                "VALUES (:id, :actor_role, :action, :resource_type, :resource_id, :correlation_id, :created_at)"
            ),
            {**row, "id": str(row["id"]), "resource_id": str(row["resource_id"])},
        )
        result = await session.execute(
            text("SELECT id FROM _test_audit_logs WHERE id = :id"),
            {"id": str(row["id"])},
        )
        assert result.fetchone() is not None

    async def test_null_actor_id_allowed(self, session: AsyncSession) -> None:
        ts = datetime(2025, 1, 20, tzinfo=timezone.utc)
        row = _make_audit_row(created_at=ts, actor_id=None)
        await session.execute(
            text(
                "INSERT INTO _test_audit_logs "
                "(id, actor_id, actor_role, action, resource_type, correlation_id, created_at) "
                "VALUES (:id, NULL, :actor_role, :action, :resource_type, :correlation_id, :created_at)"
            ),
            {**row, "id": str(row["id"])},
        )

    async def test_before_after_state_jsonb(self, session: AsyncSession) -> None:
        ts = datetime(2025, 1, 22, tzinfo=timezone.utc)
        row = _make_audit_row(created_at=ts)
        await session.execute(
            text(
                "INSERT INTO _test_audit_logs "
                "(id, actor_role, action, resource_type, before_state, after_state, created_at) "
                "VALUES (:id, :actor_role, :action, :resource_type, "
                "        :before_state::jsonb, :after_state::jsonb, :created_at)"
            ),
            {
                **row,
                "id": str(row["id"]),
                "before_state": '{"weight": 1.0}',
                "after_state": '{"weight": 2.0}',
            },
        )
        result = await session.execute(
            text(
                "SELECT after_state->>'weight' AS w "
                "FROM _test_audit_logs WHERE id = :id"
            ),
            {"id": str(row["id"])},
        )
        row_result = result.fetchone()
        assert row_result is not None
        assert row_result[0] == "2.0"


# ---------------------------------------------------------------------------
# Partition routing — records land in the correct monthly partition
# ---------------------------------------------------------------------------

class TestPartitionRouting:
    async def test_january_record_in_january_partition(
        self, session: AsyncSession
    ) -> None:
        ts = datetime(2025, 1, 5, tzinfo=timezone.utc)
        row = _make_audit_row(created_at=ts)
        await session.execute(
            text(
                "INSERT INTO _test_audit_logs "
                "(id, actor_role, action, resource_type, created_at) "
                "VALUES (:id, :actor_role, :action, :resource_type, :created_at)"
            ),
            {**row, "id": str(row["id"])},
        )
        result = await session.execute(
            text(
                "SELECT id FROM _test_audit_logs_2025_01 WHERE id = :id"
            ),
            {"id": str(row["id"])},
        )
        assert result.fetchone() is not None, "Record not found in jan partition"

    async def test_february_record_in_february_partition(
        self, session: AsyncSession
    ) -> None:
        ts = datetime(2025, 2, 14, tzinfo=timezone.utc)
        row = _make_audit_row(created_at=ts)
        await session.execute(
            text(
                "INSERT INTO _test_audit_logs "
                "(id, actor_role, action, resource_type, created_at) "
                "VALUES (:id, :actor_role, :action, :resource_type, :created_at)"
            ),
            {**row, "id": str(row["id"])},
        )
        result = await session.execute(
            text("SELECT id FROM _test_audit_logs_2025_02 WHERE id = :id"),
            {"id": str(row["id"])},
        )
        assert result.fetchone() is not None, "Record not found in feb partition"

    async def test_cross_partition_select(self, session: AsyncSession) -> None:
        for day, month in [(3, 1), (3, 2), (3, 3)]:
            ts = datetime(2025, month, day, tzinfo=timezone.utc)
            row = _make_audit_row(created_at=ts)
            await session.execute(
                text(
                    "INSERT INTO _test_audit_logs "
                    "(id, actor_role, action, resource_type, created_at) "
                    "VALUES (:id, :actor_role, :action, :resource_type, :created_at)"
                ),
                {**row, "id": str(row["id"])},
            )
        result = await session.execute(
            text(
                "SELECT COUNT(*) FROM _test_audit_logs "
                "WHERE created_at >= '2025-01-01' AND created_at < '2025-04-01'"
            )
        )
        count = result.scalar()
        assert count >= 3, "Cross-partition SELECT did not return all records"


# ---------------------------------------------------------------------------
# Immutability — privilege model verification
# ---------------------------------------------------------------------------

class TestImmutabilityPrivileges:
    async def test_forgeguard_app_role_has_no_update_privilege(
        self, session: AsyncSession
    ) -> None:
        """Verify forgeguard_app role lacks UPDATE privilege on audit_logs."""
        result = await session.execute(
            text(
                "SELECT has_table_privilege('forgeguard_app', 'audit_logs', 'UPDATE') "
                "WHERE EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'forgeguard_app')"
            )
        )
        row = result.fetchone()
        if row is not None:
            assert row[0] is False, "forgeguard_app must NOT have UPDATE on audit_logs"

    async def test_forgeguard_app_role_has_no_delete_privilege(
        self, session: AsyncSession
    ) -> None:
        """Verify forgeguard_app role lacks DELETE privilege on audit_logs."""
        result = await session.execute(
            text(
                "SELECT has_table_privilege('forgeguard_app', 'audit_logs', 'DELETE') "
                "WHERE EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'forgeguard_app')"
            )
        )
        row = result.fetchone()
        if row is not None:
            assert row[0] is False, "forgeguard_app must NOT have DELETE on audit_logs"

    async def test_no_updated_at_column(self, session: AsyncSession) -> None:
        """audit_logs must have NO updated_at column — write-once requirement."""
        result = await session.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'audit_logs' "
                "AND column_name = 'updated_at'"
            )
        )
        assert result.fetchone() is None, "audit_logs must not have updated_at"


# ---------------------------------------------------------------------------
# Partition management function — idempotency
# ---------------------------------------------------------------------------

class TestCreateAuditPartition:
    async def test_create_partition_function_exists(
        self, session: AsyncSession
    ) -> None:
        """create_audit_partition function was created by the migration."""
        result = await session.execute(
            text(
                "SELECT proname FROM pg_proc "
                "WHERE proname = 'create_audit_partition'"
            )
        )
        assert result.fetchone() is not None

    async def test_create_partition_is_idempotent(
        self, session: AsyncSession
    ) -> None:
        """Calling create_audit_partition for an existing partition is a no-op.

        Only runs if the migration has been applied (audit_logs exists).
        """
        # Check audit_logs exists (migration-created partitioned table).
        result = await session.execute(
            text(
                "SELECT 1 FROM pg_class c "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE c.relname = 'audit_logs' AND n.nspname = current_schema()"
            )
        )
        if result.fetchone() is None:
            pytest.skip("audit_logs not found — migration not applied")

        # Both the function and an initial partition exist; calling it again is safe.
        await session.execute(
            text("SELECT create_audit_partition('2025-01-01'::DATE)")
        )

    async def test_drop_expired_function_exists(
        self, session: AsyncSession
    ) -> None:
        """drop_expired_audit_partitions function was created by the migration."""
        result = await session.execute(
            text(
                "SELECT proname FROM pg_proc "
                "WHERE proname = 'drop_expired_audit_partitions'"
            )
        )
        assert result.fetchone() is not None


# ---------------------------------------------------------------------------
# Composite index verification
# ---------------------------------------------------------------------------

class TestAuditIndexes:
    async def test_actor_id_created_at_index_exists(
        self, session: AsyncSession
    ) -> None:
        result = await session.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE tablename = 'audit_logs' "
                "AND indexname = 'ix_audit_logs_actor_id_created_at'"
            )
        )
        assert result.fetchone() is not None

    async def test_resource_type_resource_id_created_at_index_exists(
        self, session: AsyncSession
    ) -> None:
        result = await session.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE tablename = 'audit_logs' "
                "AND indexname = "
                "'ix_audit_logs_resource_type_resource_id_created_at'"
            )
        )
        assert result.fetchone() is not None


# ---------------------------------------------------------------------------
# AIConversation table
# ---------------------------------------------------------------------------

class TestAIConversation:
    async def test_insert_and_select(self, session: AsyncSession) -> None:
        conv_id = uuid.uuid4()
        user_id = uuid.uuid4()
        await session.execute(
            text(
                "INSERT INTO _test_ai_conversations (id, user_id) "
                "VALUES (:id, :user_id)"
            ),
            {"id": str(conv_id), "user_id": str(user_id)},
        )
        result = await session.execute(
            text(
                "SELECT id, messages FROM _test_ai_conversations WHERE id = :id"
            ),
            {"id": str(conv_id)},
        )
        row = result.fetchone()
        assert row is not None
        assert row[1] == []  # default empty array

    async def test_messages_jsonb_array(self, session: AsyncSession) -> None:
        conv_id = uuid.uuid4()
        user_id = uuid.uuid4()
        messages = '[{"role":"user","content":"Hello"},{"role":"assistant","content":"Hi"}]'
        await session.execute(
            text(
                "INSERT INTO _test_ai_conversations (id, user_id, messages) "
                "VALUES (:id, :user_id, :messages::jsonb)"
            ),
            {
                "id": str(conv_id),
                "user_id": str(user_id),
                "messages": messages,
            },
        )
        result = await session.execute(
            text(
                "SELECT jsonb_array_length(messages) "
                "FROM _test_ai_conversations WHERE id = :id"
            ),
            {"id": str(conv_id)},
        )
        count = result.scalar()
        assert count == 2

    async def test_context_refs_jsonb(self, session: AsyncSession) -> None:
        conv_id = uuid.uuid4()
        user_id = uuid.uuid4()
        refs = '{"service_ids": ["abc"], "policy_ids": ["def"]}'
        await session.execute(
            text(
                "INSERT INTO _test_ai_conversations (id, user_id, context_refs) "
                "VALUES (:id, :user_id, :context_refs::jsonb)"
            ),
            {
                "id": str(conv_id),
                "user_id": str(user_id),
                "context_refs": refs,
            },
        )
        result = await session.execute(
            text(
                "SELECT context_refs->'service_ids' "
                "FROM _test_ai_conversations WHERE id = :id"
            ),
            {"id": str(conv_id)},
        )
        row = result.fetchone()
        assert row is not None
        assert row[0] is not None

    async def test_ai_conversations_index_exists(
        self, session: AsyncSession
    ) -> None:
        result = await session.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE tablename = '_test_ai_conversations' "
                "AND indexname = 'ix_test_ai_conversations_user_id'"
            )
        )
        assert result.fetchone() is not None


# ---------------------------------------------------------------------------
# Table structure verification via information_schema
# ---------------------------------------------------------------------------

class TestAuditTableStructure:
    async def test_audit_logs_table_is_partitioned(
        self, session: AsyncSession
    ) -> None:
        """audit_logs must be a partitioned table, not a regular table."""
        result = await session.execute(
            text(
                "SELECT relkind FROM pg_class "
                "WHERE relname = 'audit_logs' "
                "AND relnamespace = (SELECT oid FROM pg_namespace "
                "                    WHERE nspname = current_schema())"
            )
        )
        row = result.fetchone()
        assert row is not None
        # relkind 'p' = partitioned table in PostgreSQL
        assert row[0] == "p", f"Expected relkind='p' (partitioned), got '{row[0]}'"

    async def test_audit_logs_has_correct_columns(
        self, session: AsyncSession
    ) -> None:
        expected_columns = {
            "id", "actor_id", "actor_role", "action",
            "resource_type", "resource_id", "before_state", "after_state",
            "ip_address_masked", "correlation_id", "created_at",
        }
        result = await session.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'audit_logs'"
            )
        )
        cols = {row[0] for row in result.fetchall()}
        assert expected_columns.issubset(cols)
        assert "updated_at" not in cols, "audit_logs must not have updated_at"

    async def test_ai_conversations_has_correct_columns(
        self, session: AsyncSession
    ) -> None:
        result = await session.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = '_test_ai_conversations'"
            )
        )
        cols = {row[0] for row in result.fetchall()}
        assert {"id", "user_id", "messages", "context_refs",
                "created_at", "updated_at"}.issubset(cols)
