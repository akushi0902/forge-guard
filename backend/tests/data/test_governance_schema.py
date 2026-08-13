"""Schema-level tests for the Governance domain tables.

All tests require a live PostgreSQL instance and are automatically skipped
when the database is unreachable so the standard unit-test suite runs without
infrastructure dependencies.

Tests exercise:
    1. Service INSERT / SELECT / soft-delete.
    2. Unique constraint on services.name.
    3. Policy INSERT with all valid dimensions.
    4. CHECK constraint on policies.dimension rejects invalid values.
    5. FK cascade: deleting a Policy removes its PolicyRules.
    6. PolicyRule INSERT with JSONB threshold_config.
    7. CHECK constraint on policy_rules.severity rejects invalid values.
    8. JSONB threshold_config accepts deeply-nested objects.
    9. GIN index is present (verified via pg_indexes catalog).
    10. Composite index on (policy_id, is_active) is present.
    11. Integration: migration creates all three Governance tables.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from forgeguard.core.config import get_settings
from forgeguard.data.models import Base, Policy, PolicyRule, Service, User
from forgeguard.data.models.governance import VALID_DIMENSIONS, VALID_SEVERITIES


# ---------------------------------------------------------------------------
# Database availability guard — skip all tests when no DB is reachable.
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
# Module-scoped engine + session fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(scope="module")
async def db_engine():
    """Create all tables, yield engine, then drop all tables."""
    engine = create_async_engine(get_settings().database_url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture()
async def session(db_engine):
    """Yield an AsyncSession rolled back after each test for isolation."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as sess:
        async with sess.begin():
            yield sess
            await sess.rollback()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(**kwargs) -> User:
    defaults = {
        "id": uuid.uuid4(),
        "email": f"gov-{uuid.uuid4().hex[:8]}@example.com",
        "password_hash": "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8y7.xXj4pF.mY0gLXWc",
        "role": "tech_lead",
        "is_active": True,
        "failed_login_attempts": 0,
    }
    defaults.update(kwargs)
    return User(**defaults)


def _make_service(**kwargs) -> Service:
    defaults = {
        "id": uuid.uuid4(),
        "name": f"svc-{uuid.uuid4().hex[:8]}",
        "is_demo": False,
    }
    defaults.update(kwargs)
    return Service(**defaults)


def _make_policy(service_id: uuid.UUID | None = None, **kwargs) -> Policy:
    defaults = {
        "id": uuid.uuid4(),
        "name": f"policy-{uuid.uuid4().hex[:8]}",
        "dimension": "code_quality",
        "service_id": service_id,
    }
    defaults.update(kwargs)
    return Policy(**defaults)


def _make_rule(policy_id: uuid.UUID, **kwargs) -> PolicyRule:
    defaults = {
        "id": uuid.uuid4(),
        "policy_id": policy_id,
        "name": f"rule-{uuid.uuid4().hex[:8]}",
        "rule_type": "threshold",
        "threshold_config": {"operator": "gte", "value": 80, "unit": "percent"},
        "severity": "medium",
        "weight": Decimal("1.0"),
    }
    defaults.update(kwargs)
    return PolicyRule(**defaults)


# ---------------------------------------------------------------------------
# Service table
# ---------------------------------------------------------------------------

class TestServiceInsert:
    async def test_insert_minimal_service(self, session: AsyncSession) -> None:
        svc = _make_service()
        session.add(svc)
        await session.flush()
        result = await session.get(Service, svc.id)
        assert result is not None
        assert result.name == svc.name

    async def test_service_defaults(self, session: AsyncSession) -> None:
        svc = _make_service()
        session.add(svc)
        await session.flush()
        result = await session.get(Service, svc.id)
        assert result is not None
        assert result.is_demo is False
        assert result.deleted_at is None
        assert result.forge_catalog_id is None
        assert result.service_metadata == {}

    async def test_service_jsonb_metadata(self, session: AsyncSession) -> None:
        svc = _make_service(service_metadata={"language": "Python", "team_size": 5})
        session.add(svc)
        await session.flush()
        result = await session.get(Service, svc.id)
        assert result is not None
        assert result.service_metadata["language"] == "Python"
        assert result.service_metadata["team_size"] == 5

    async def test_service_is_demo_true(self, session: AsyncSession) -> None:
        svc = _make_service(is_demo=True, name="Payment Service")
        session.add(svc)
        await session.flush()
        result = await session.get(Service, svc.id)
        assert result is not None
        assert result.is_demo is True

    async def test_service_soft_delete(self, session: AsyncSession) -> None:
        svc = _make_service(deleted_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
        session.add(svc)
        await session.flush()
        result = await session.get(Service, svc.id)
        assert result is not None
        assert result.deleted_at is not None


class TestServiceConstraints:
    async def test_unique_name_constraint(self, session: AsyncSession) -> None:
        name = f"duplicate-{uuid.uuid4().hex[:6]}"
        svc_a = _make_service(name=name)
        svc_b = _make_service(name=name)
        session.add(svc_a)
        await session.flush()
        session.add(svc_b)
        with pytest.raises(IntegrityError, match="uq_services_name|unique"):
            await session.flush()

    async def test_null_name_rejected(self, session: AsyncSession) -> None:
        svc = _make_service()
        svc.name = None  # type: ignore[assignment]
        session.add(svc)
        with pytest.raises(IntegrityError):
            await session.flush()


# ---------------------------------------------------------------------------
# Policy table
# ---------------------------------------------------------------------------

class TestPolicyDimensions:
    async def test_all_valid_dimensions_accepted(self, session: AsyncSession) -> None:
        for dimension in VALID_DIMENSIONS:
            policy = _make_policy(dimension=dimension)
            session.add(policy)
        await session.flush()

    async def test_invalid_dimension_rejected(self, session: AsyncSession) -> None:
        policy = _make_policy(dimension="invalid_dimension")
        session.add(policy)
        with pytest.raises(
            IntegrityError, match="ck_policies_valid_dimension|check"
        ):
            await session.flush()

    async def test_policy_defaults(self, session: AsyncSession) -> None:
        policy = _make_policy()
        session.add(policy)
        await session.flush()
        result = await session.get(Policy, policy.id)
        assert result is not None
        assert result.is_active is True
        assert result.version == 1
        assert result.deleted_at is None
        assert result.created_by is None

    async def test_policy_created_by_fk(self, session: AsyncSession) -> None:
        user = _make_user()
        session.add(user)
        await session.flush()

        policy = _make_policy(created_by=user.id)
        session.add(policy)
        await session.flush()
        result = await session.get(Policy, policy.id)
        assert result is not None
        assert result.created_by == user.id


# ---------------------------------------------------------------------------
# PolicyRule table — CHECK constraint on severity
# ---------------------------------------------------------------------------

class TestPolicyRuleSeverity:
    async def test_all_valid_severities_accepted(self, session: AsyncSession) -> None:
        policy = _make_policy()
        session.add(policy)
        await session.flush()

        for severity in VALID_SEVERITIES:
            rule = _make_rule(policy_id=policy.id, severity=severity)
            session.add(rule)
        await session.flush()

    async def test_invalid_severity_rejected(self, session: AsyncSession) -> None:
        policy = _make_policy()
        session.add(policy)
        await session.flush()

        rule = _make_rule(policy_id=policy.id, severity="negligible")
        session.add(rule)
        with pytest.raises(
            IntegrityError, match="ck_policy_rules_valid_severity|check"
        ):
            await session.flush()


# ---------------------------------------------------------------------------
# PolicyRule — JSONB threshold_config
# ---------------------------------------------------------------------------

class TestPolicyRuleJsonb:
    async def test_simple_threshold_config(self, session: AsyncSession) -> None:
        policy = _make_policy()
        session.add(policy)
        await session.flush()

        config = {"operator": "gte", "value": 80, "unit": "percent"}
        rule = _make_rule(policy_id=policy.id, threshold_config=config)
        session.add(rule)
        await session.flush()

        result = await session.get(PolicyRule, rule.id)
        assert result is not None
        assert result.threshold_config["operator"] == "gte"
        assert result.threshold_config["value"] == 80

    async def test_deeply_nested_jsonb_config(self, session: AsyncSession) -> None:
        policy = _make_policy()
        session.add(policy)
        await session.flush()

        deep_config = {
            "operator": "gte",
            "value": 95,
            "unit": "percent",
            "conditions": {
                "exclude_files": ["**/test_*.py", "**/conftest.py"],
                "minimum_lines": 10,
                "branches": {
                    "enabled": True,
                    "threshold": 80,
                    "policy": {"strict": True, "report": "full"},
                },
            },
        }
        rule = _make_rule(policy_id=policy.id, threshold_config=deep_config)
        session.add(rule)
        await session.flush()

        result = await session.get(PolicyRule, rule.id)
        assert result is not None
        assert result.threshold_config["conditions"]["branches"]["policy"]["strict"] is True

    async def test_jsonb_containment_query(self, session: AsyncSession) -> None:
        policy = _make_policy()
        session.add(policy)
        await session.flush()

        rule = _make_rule(
            policy_id=policy.id,
            threshold_config={"operator": "gte", "value": 80, "unit": "percent"},
        )
        session.add(rule)
        await session.flush()

        result = await session.execute(
            text(
                "SELECT id FROM policy_rules "
                "WHERE threshold_config @> '{\"operator\": \"gte\"}'::jsonb"
            )
        )
        rows = result.fetchall()
        assert len(rows) >= 1


# ---------------------------------------------------------------------------
# FK CASCADE: deleting a Policy removes its PolicyRules
# ---------------------------------------------------------------------------

class TestPolicyCascade:
    async def test_delete_policy_cascades_to_rules(
        self, session: AsyncSession
    ) -> None:
        policy = _make_policy()
        session.add(policy)
        await session.flush()

        rule1 = _make_rule(policy_id=policy.id)
        rule2 = _make_rule(policy_id=policy.id)
        session.add_all([rule1, rule2])
        await session.flush()

        rule1_id = rule1.id
        rule2_id = rule2.id

        await session.delete(policy)
        await session.flush()

        assert await session.get(PolicyRule, rule1_id) is None
        assert await session.get(PolicyRule, rule2_id) is None

    async def test_rule_fk_to_nonexistent_policy_rejected(
        self, session: AsyncSession
    ) -> None:
        rule = _make_rule(policy_id=uuid.uuid4())
        session.add(rule)
        with pytest.raises(
            IntegrityError, match="fk_policy_rules_policy_id_policies|foreign key"
        ):
            await session.flush()


# ---------------------------------------------------------------------------
# Index verification via PostgreSQL catalog
# ---------------------------------------------------------------------------

class TestIndexes:
    async def test_gin_index_exists_on_threshold_config(
        self, session: AsyncSession
    ) -> None:
        result = await session.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE tablename = 'policy_rules' "
                "AND indexname = 'ix_policy_rules_threshold_config_gin'"
            )
        )
        row = result.fetchone()
        assert row is not None, "GIN index on policy_rules.threshold_config not found"

    async def test_composite_index_exists_on_policy_id_is_active(
        self, session: AsyncSession
    ) -> None:
        result = await session.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE tablename = 'policy_rules' "
                "AND indexname = 'ix_policy_rules_policy_id_is_active'"
            )
        )
        row = result.fetchone()
        assert row is not None, (
            "Composite index on policy_rules(policy_id, is_active) not found"
        )

    async def test_unique_index_exists_on_services_name(
        self, session: AsyncSession
    ) -> None:
        result = await session.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE tablename = 'services' "
                "AND indexname = 'uq_services_name'"
            )
        )
        row = result.fetchone()
        assert row is not None, "Unique index on services.name not found"


# ---------------------------------------------------------------------------
# Integration: all three Governance tables exist
# ---------------------------------------------------------------------------

class TestTableExistence:
    async def test_services_table_exists(self, session: AsyncSession) -> None:
        result = await session.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name = 'services'"
            )
        )
        assert result.fetchone() is not None

    async def test_policies_table_exists(self, session: AsyncSession) -> None:
        result = await session.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name = 'policies'"
            )
        )
        assert result.fetchone() is not None

    async def test_policy_rules_table_exists(self, session: AsyncSession) -> None:
        result = await session.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name = 'policy_rules'"
            )
        )
        assert result.fetchone() is not None

    async def test_services_metadata_column_is_jsonb(
        self, session: AsyncSession
    ) -> None:
        result = await session.execute(
            text(
                "SELECT data_type FROM information_schema.columns "
                "WHERE table_name = 'services' AND column_name = 'metadata'"
            )
        )
        row = result.fetchone()
        assert row is not None
        assert row[0] == "jsonb"

    async def test_policy_rules_threshold_config_is_jsonb(
        self, session: AsyncSession
    ) -> None:
        result = await session.execute(
            text(
                "SELECT data_type FROM information_schema.columns "
                "WHERE table_name = 'policy_rules' "
                "AND column_name = 'threshold_config'"
            )
        )
        row = result.fetchone()
        assert row is not None
        assert row[0] == "jsonb"

    async def test_policy_rules_weight_is_numeric(
        self, session: AsyncSession
    ) -> None:
        result = await session.execute(
            text(
                "SELECT data_type FROM information_schema.columns "
                "WHERE table_name = 'policy_rules' AND column_name = 'weight'"
            )
        )
        row = result.fetchone()
        assert row is not None
        assert row[0] == "numeric"
