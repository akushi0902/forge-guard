"""Smoke tests for the pytest test infrastructure (unit scope — no Docker required).

These tests verify that:
1. pytest-asyncio async tests work correctly.
2. The test_client fixture yields a usable httpx.AsyncClient.
3. The authenticated_client fixture yields clients with Bearer tokens.
4. All factory classes can be instantiated in-memory.
5. Factory-generated data is structurally valid (correct types, non-empty values).

None of these tests require a live database or Docker.
"""

from __future__ import annotations

import uuid

import pytest

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
# 1. pytest-asyncio — async test infrastructure
# ---------------------------------------------------------------------------

@pytest.mark.unit
async def test_async_test_runs():
    """Verify that async def test functions execute correctly."""
    result = await _async_double(21)
    assert result == 42


async def _async_double(n: int) -> int:
    return n * 2


# ---------------------------------------------------------------------------
# 2. test_client fixture
# ---------------------------------------------------------------------------

@pytest.mark.unit
async def test_test_client_health(test_client):
    """test_client can reach GET /health and receive a 200 response."""
    response = await test_client.get("/health")
    assert response.status_code == 200


@pytest.mark.unit
async def test_test_client_returns_json(test_client):
    """GET /health returns a JSON body with a 'status' field."""
    response = await test_client.get("/health")
    body = response.json()
    assert "status" in body


@pytest.mark.unit
async def test_test_client_is_reusable(test_client):
    """The test_client fixture can be called multiple times in one test."""
    r1 = await test_client.get("/health")
    r2 = await test_client.get("/health")
    assert r1.status_code == r2.status_code == 200


# ---------------------------------------------------------------------------
# 3. authenticated_client fixture
# ---------------------------------------------------------------------------

@pytest.mark.unit
async def test_authenticated_client_has_auth_header(authenticated_client):
    """authenticated_client injects an Authorization: Bearer ... header."""
    client = await authenticated_client("developer")
    # The header is present in the client's default headers.
    assert "authorization" in {h.lower() for h in client.headers}
    assert client.headers["authorization"].startswith("Bearer ")


@pytest.mark.unit
async def test_authenticated_client_different_roles(authenticated_client):
    """Different role strings produce different tokens."""
    dev_client = await authenticated_client("developer")
    lead_client = await authenticated_client("tech_lead")
    assert dev_client.headers["authorization"] != lead_client.headers["authorization"]


@pytest.mark.unit
async def test_authenticated_client_can_reach_health(authenticated_client):
    """An authenticated client can still reach public endpoints like /health."""
    client = await authenticated_client("operator")
    response = await client.get("/health")
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# 4. Factory instantiation (no DB)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_user_factory_build():
    """UserFactory.build() creates a User object in-memory without a session."""
    user = UserFactory.build()
    assert isinstance(user.id, uuid.UUID)
    assert "@" in user.email
    assert user.password_hash.startswith("$2b$")
    assert len(user.password_hash) == 60
    assert user.role in (
        "developer", "tech_lead", "security_reviewer",
        "platform_admin", "engineering_manager", "operator",
    )
    assert user.is_active is True
    assert user.failed_login_attempts == 0


@pytest.mark.unit
def test_service_factory_build():
    """ServiceFactory.build() creates a ServiceData object."""
    svc = ServiceFactory.build()
    assert isinstance(svc.id, uuid.UUID)
    assert svc.name
    assert svc.team
    assert svc.repository_url.startswith("https://")


@pytest.mark.unit
def test_policy_rule_factory_build():
    """PolicyRuleFactory.build() creates a PolicyRuleData object."""
    rule = PolicyRuleFactory.build()
    assert isinstance(rule.id, uuid.UUID)
    assert rule.name
    assert rule.dimension in (
        "test_coverage", "documentation", "security",
        "dependency_health", "code_quality",
    )
    assert rule.severity in ("critical", "high", "medium", "low", "info")
    assert 50.0 <= rule.threshold <= 100.0
    assert rule.is_enabled is True


@pytest.mark.unit
def test_finding_factory_build():
    """FindingFactory.build() creates a FindingData object."""
    finding = FindingFactory.build()
    assert isinstance(finding.id, uuid.UUID)
    assert isinstance(finding.service_id, uuid.UUID)
    assert isinstance(finding.policy_rule_id, uuid.UUID)
    assert finding.title
    assert finding.description
    assert finding.status in ("open", "in_progress", "resolved", "excepted")


@pytest.mark.unit
def test_assessment_factory_build():
    """AssessmentFactory.build() creates an AssessmentData object."""
    assessment = AssessmentFactory.build()
    assert isinstance(assessment.id, uuid.UUID)
    assert len(assessment.commit_sha) == 40
    assert 0.0 <= assessment.health_score <= 100.0
    assert 0.0 <= assessment.risk_score <= 100.0
    assert assessment.decision in ("approve", "conditional_approve", "block", "pending")


@pytest.mark.unit
def test_release_decision_factory_build():
    """ReleaseDecisionFactory.build() creates a ReleaseDecisionData object."""
    decision = ReleaseDecisionFactory.build()
    assert isinstance(decision.id, uuid.UUID)
    assert decision.rationale
    assert isinstance(decision.conditions, list)


@pytest.mark.unit
def test_audit_log_factory_build():
    """AuditLogFactory.build() creates an AuditLogData object."""
    log = AuditLogFactory.build()
    assert isinstance(log.id, uuid.UUID)
    assert isinstance(log.actor_id, uuid.UUID)
    assert log.action
    assert log.resource_type
    assert log.ip_address


# ---------------------------------------------------------------------------
# 5. Factory uniqueness
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_user_factory_generates_unique_emails():
    """Each UserFactory.build() call produces a distinct email address."""
    users = [UserFactory.build() for _ in range(10)]
    emails = [u.email for u in users]
    assert len(set(emails)) == 10, "Duplicate emails across factory-built users"


@pytest.mark.unit
def test_user_factory_generates_unique_ids():
    """Each UserFactory.build() call produces a distinct UUID."""
    users = [UserFactory.build() for _ in range(5)]
    ids = [str(u.id) for u in users]
    assert len(set(ids)) == 5
