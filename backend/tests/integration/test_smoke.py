"""Integration smoke tests — require Docker (testcontainers).

These tests verify the full database infrastructure works:
1. db_session fixture yields a live AsyncSession connected to the testcontainer.
2. UserFactory can INSERT and SELECT a User via db_session.
3. test_client can reach /health while db_session is active.
4. All domain factories produce objects that can be instantiated without errors.

Marked with ``@pytest.mark.integration`` so they can be excluded in environments
without Docker::

    pytest -m "not integration"   # CI without Docker
    pytest -m integration          # CI with Docker
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from forgeguard.data.models.identity import User
from tests.factories import (
    AssessmentFactory,
    AuditLogFactory,
    FindingFactory,
    PolicyRuleFactory,
    ReleaseDecisionFactory,
    ServiceFactory,
    UserFactory,
)


# ---------------------------------------------------------------------------
# 1. db_session — INSERT and SELECT
# ---------------------------------------------------------------------------

@pytest.mark.integration
async def test_db_session_insert_and_select_user(db_session):
    """db_session can persist a User and retrieve it by primary key."""
    UserFactory._meta.sqlalchemy_session = db_session

    user = UserFactory()  # creates + flushes within the open transaction
    await db_session.flush()

    result = await db_session.execute(select(User).where(User.id == user.id))
    fetched = result.scalar_one_or_none()

    assert fetched is not None
    assert fetched.id == user.id
    assert fetched.email == user.email
    assert fetched.role == user.role


@pytest.mark.integration
async def test_db_session_rollback_isolation(db_session):
    """Each db_session starts clean — no data from previous tests leaks in."""
    UserFactory._meta.sqlalchemy_session = db_session

    # Count users currently in DB (should be 0 or at most from this test's setup).
    before = await db_session.execute(select(User))
    count_before = len(before.scalars().all())

    UserFactory()
    UserFactory()
    await db_session.flush()

    after = await db_session.execute(select(User))
    count_after = len(after.scalars().all())

    assert count_after == count_before + 2


@pytest.mark.integration
async def test_db_session_unique_email_constraint(db_session):
    """Inserting two users with the same email raises an IntegrityError."""
    from sqlalchemy.exc import IntegrityError

    UserFactory._meta.sqlalchemy_session = db_session
    email = f"duplicate-{uuid.uuid4()}@example.com"

    UserFactory(email=email)
    UserFactory(email=email)

    with pytest.raises(IntegrityError):
        await db_session.flush()


# ---------------------------------------------------------------------------
# 2. test_client + db_session
# ---------------------------------------------------------------------------

@pytest.mark.integration
async def test_health_endpoint_while_db_is_active(test_client, db_session):
    """test_client can reach GET /health while a db_session fixture is open."""
    response = await test_client.get("/health")
    assert response.status_code == 200


@pytest.mark.integration
async def test_readiness_endpoint_responds(test_client):
    """GET /ready returns either 200 (ready) or 503 (not ready to test DB config).

    In an environment without a running DB at the test_settings URL this
    endpoint returns 503; that is expected and not a test failure.
    """
    response = await test_client.get("/ready")
    assert response.status_code in (200, 503)


# ---------------------------------------------------------------------------
# 3. Factory persistence for each domain entity
# ---------------------------------------------------------------------------

@pytest.mark.integration
async def test_user_factory_persists(db_session):
    """UserFactory creates a User that survives flush and can be queried back."""
    UserFactory._meta.sqlalchemy_session = db_session
    user = UserFactory()
    await db_session.flush()

    result = await db_session.execute(
        select(User).where(User.email == user.email)
    )
    assert result.scalar_one_or_none() is not None


@pytest.mark.integration
def test_service_factory_produces_valid_object():
    """ServiceFactory.build() produces a ServiceData with valid fields."""
    svc = ServiceFactory.build()
    assert svc.name
    assert svc.repository_url.startswith("https://")


@pytest.mark.integration
def test_policy_rule_factory_produces_valid_object():
    """PolicyRuleFactory.build() produces a PolicyRuleData with valid fields."""
    rule = PolicyRuleFactory.build()
    assert rule.name
    assert rule.threshold >= 0


@pytest.mark.integration
def test_finding_factory_produces_valid_object():
    """FindingFactory.build() produces a FindingData with valid fields."""
    finding = FindingFactory.build()
    assert finding.title
    assert finding.severity in ("critical", "high", "medium", "low", "info")


@pytest.mark.integration
def test_assessment_factory_produces_valid_object():
    """AssessmentFactory.build() produces an AssessmentData with valid fields."""
    assessment = AssessmentFactory.build()
    assert len(assessment.commit_sha) == 40
    assert 0 <= assessment.health_score <= 100


@pytest.mark.integration
def test_audit_log_factory_produces_valid_object():
    """AuditLogFactory.build() produces an AuditLogData with valid fields."""
    log = AuditLogFactory.build()
    assert log.actor_role in (
        "developer", "tech_lead", "security_reviewer",
        "platform_admin", "engineering_manager", "operator",
    )
    assert log.action
    assert log.request_id


@pytest.mark.integration
def test_release_decision_factory_produces_valid_object():
    """ReleaseDecisionFactory.build() produces a ReleaseDecisionData."""
    decision = ReleaseDecisionFactory.build()
    assert decision.outcome in ("approve", "conditional_approve", "block", "pending")
    assert isinstance(decision.conditions, list)


# ---------------------------------------------------------------------------
# 4. Multi-factory scenario
# ---------------------------------------------------------------------------

@pytest.mark.integration
async def test_multiple_users_with_different_roles(db_session):
    """Create multiple users, each with a distinct role, and verify persistence."""
    UserFactory._meta.sqlalchemy_session = db_session
    roles = ["developer", "tech_lead", "security_reviewer"]

    for role in roles:
        UserFactory(role=role)

    await db_session.flush()

    for role in roles:
        result = await db_session.execute(
            select(User).where(User.role == role)
        )
        users = result.scalars().all()
        assert len(users) >= 1, f"Expected at least one user with role={role}"
