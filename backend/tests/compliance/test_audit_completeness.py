"""Audit log completeness compliance test suite (WO-099).

Verifies that AuditService produces complete, correctly-populated audit records
for every category of data mutation and authentication event required by SOC 2
and GDPR.

Since the mutation HTTP endpoints (services, policies, assessments, etc.) are
not yet implemented, these tests verify audit completeness by exercising the
AuditService write path directly.  This is the authoritative write path; the
middleware and HTTP layer are thin wrappers over it.

Compliance scope:
  1. Service CRUD — create, update, delete each produce exactly one record.
  2. Policy CRUD — same pattern.
  3. Assessment lifecycle — create and complete each produce one record.
  4. Decision actions — approve/block release each produce one record.
  5. Exception lifecycle — create and approve each produce one record.
  6. RBAC changes — role assignment produces one record with before/after state.
  7. Auth events — login, login failure, logout, token refresh each produce one record.
  8. All required fields — id, actor_id, actor_role, action, resource_type,
     resource_id, before_state, after_state, ip_address_masked, correlation_id,
     created_at — are present and correctly typed.
  9. before_state null for creates; after_state null for deletes; both set for updates.
 10. Completeness ratio — N mutations produce exactly N audit records (1:1).
 11. Correlation ID — value passed to log_event is stored verbatim (truncated at 36).

Tests require Docker (PostgreSQL testcontainer) and are tagged integration.

Run:
    pytest tests/compliance/test_audit_completeness.py -v -m integration
"""

from __future__ import annotations

import uuid
from typing import Any, Callable, Coroutine

import pytest

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Helper: assert exactly one audit record is created by an operation
# ---------------------------------------------------------------------------


async def assert_audit_record_created(
    pool,
    operation: Callable[[], Coroutine[Any, Any, Any]],
) -> dict[str, Any]:
    """Assert that *operation* produces exactly one new audit_logs row.

    Counts rows before and after calling *operation*, asserts the delta is 1,
    and returns the newly created record for field-level assertions.
    """
    async with pool.acquire() as conn:
        count_before: int = await conn.fetchval("SELECT COUNT(*) FROM audit_logs")

    await operation()

    async with pool.acquire() as conn:
        count_after: int = await conn.fetchval("SELECT COUNT(*) FROM audit_logs")
        rows = await conn.fetch(
            "SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT 1"
        )

    delta = count_after - count_before
    assert delta == 1, (
        f"Expected exactly 1 new audit record; "
        f"found {delta} (before={count_before}, after={count_after})"
    )
    return dict(rows[0])


# ---------------------------------------------------------------------------
# Field completeness validator
# ---------------------------------------------------------------------------


def _assert_required_fields(record: dict[str, Any]) -> None:
    """Assert all non-nullable audit log fields are present and correctly typed."""
    assert record.get("id") is not None, "audit_logs.id must not be NULL"
    for field in ("actor_role", "action", "resource_type"):
        value = record.get(field)
        assert value, f"audit_logs.{field} must be a non-empty string, got {value!r}"
    assert record.get("created_at") is not None, "audit_logs.created_at must not be NULL"


# ---------------------------------------------------------------------------
# 1. Field completeness for a representative audit event (AC2)
# ---------------------------------------------------------------------------


class TestAuditLogFieldCompleteness:
    """AC2: every required field is present and correctly typed."""

    async def test_all_required_fields_present(
        self, asyncpg_pool, audit_service, audit_clean
    ):
        actor_id = uuid.uuid4()
        resource_id = uuid.uuid4()
        correlation_id = str(uuid.uuid4())

        record = await assert_audit_record_created(
            asyncpg_pool,
            lambda: audit_service.log_event(
                actor_id=actor_id,
                actor_role="developer",
                action="service.created",
                resource_type="services",
                resource_id=resource_id,
                before_state=None,
                after_state={"name": "svc-test", "is_demo": False},
                ip_address="192.168.1.100",
                correlation_id=correlation_id,
            ),
        )

        _assert_required_fields(record)
        assert record["actor_id"] == actor_id
        assert record["actor_role"] == "developer"
        assert record["action"] == "service.created"
        assert record["resource_type"] == "services"
        assert record["resource_id"] == resource_id
        assert isinstance(record["after_state"], dict)
        assert record["before_state"] is None
        assert record["ip_address_masked"] is not None
        assert "***" in record["ip_address_masked"], "IP must be masked"
        assert record["correlation_id"] == correlation_id

    async def test_before_state_null_for_create(
        self, asyncpg_pool, audit_service, audit_clean
    ):
        """AC3: before_state is NULL for create events."""
        record = await assert_audit_record_created(
            asyncpg_pool,
            lambda: audit_service.log_event(
                actor_id=uuid.uuid4(),
                actor_role="tech_lead",
                action="policy.created",
                resource_type="policies",
                resource_id=uuid.uuid4(),
                before_state=None,
                after_state={"name": "pol-1", "dimension": "code_quality"},
            ),
        )
        assert record["before_state"] is None, "before_state must be NULL for creates"
        assert record["after_state"] is not None

    async def test_after_state_null_for_delete(
        self, asyncpg_pool, audit_service, audit_clean
    ):
        """AC3: after_state is NULL for delete events."""
        record = await assert_audit_record_created(
            asyncpg_pool,
            lambda: audit_service.log_event(
                actor_id=uuid.uuid4(),
                actor_role="tech_lead",
                action="policy.deleted",
                resource_type="policies",
                resource_id=uuid.uuid4(),
                before_state={"name": "pol-1", "dimension": "code_quality"},
                after_state=None,
            ),
        )
        assert record["after_state"] is None, "after_state must be NULL for deletes"
        assert record["before_state"] is not None

    async def test_both_states_set_for_update(
        self, asyncpg_pool, audit_service, audit_clean
    ):
        """AC3: before_state and after_state both set for update events and differ."""
        before = {"name": "svc-v1", "is_demo": False}
        after = {"name": "svc-v2", "is_demo": False}

        record = await assert_audit_record_created(
            asyncpg_pool,
            lambda: audit_service.log_event(
                actor_id=uuid.uuid4(),
                actor_role="developer",
                action="service.updated",
                resource_type="services",
                resource_id=uuid.uuid4(),
                before_state=before,
                after_state=after,
            ),
        )
        assert record["before_state"] == before
        assert record["after_state"] == after
        assert record["before_state"] != record["after_state"]

    async def test_ip_address_is_masked_in_record(
        self, asyncpg_pool, audit_service, audit_clean
    ):
        """AC2: ip_address_masked stores the masked form, not the raw IP."""
        raw_ip = "10.20.30.40"
        record = await assert_audit_record_created(
            asyncpg_pool,
            lambda: audit_service.log_event(
                actor_id=uuid.uuid4(),
                actor_role="developer",
                action="service.created",
                resource_type="services",
                resource_id=uuid.uuid4(),
                ip_address=raw_ip,
            ),
        )
        stored = record["ip_address_masked"]
        assert stored is not None
        assert raw_ip not in stored, "Raw IP must not be stored — must be masked"
        assert "***" in stored


# ---------------------------------------------------------------------------
# 2. Service CRUD audit completeness (AC1)
# ---------------------------------------------------------------------------


class TestServiceCRUDAuditCompleteness:
    """AC1: service create/update/delete each produce exactly one audit record."""

    async def test_service_create_audit(
        self, asyncpg_pool, audit_service, audit_clean
    ):
        service_id = uuid.uuid4()
        record = await assert_audit_record_created(
            asyncpg_pool,
            lambda: audit_service.log_mutation(
                actor_id=uuid.uuid4(),
                actor_role="tech_lead",
                action="service.created",
                resource_type="services",
                resource_id=service_id,
                before_state=None,
                after_state={"name": "svc-alpha", "is_demo": False},
            ),
        )
        assert record["action"] == "service.created"
        assert record["resource_type"] == "services"
        assert record["resource_id"] == service_id
        assert record["before_state"] is None

    async def test_service_update_audit(
        self, asyncpg_pool, audit_service, audit_clean
    ):
        record = await assert_audit_record_created(
            asyncpg_pool,
            lambda: audit_service.log_mutation(
                actor_id=uuid.uuid4(),
                actor_role="tech_lead",
                action="service.updated",
                resource_type="services",
                resource_id=uuid.uuid4(),
                before_state={"name": "svc-alpha"},
                after_state={"name": "svc-alpha-v2"},
            ),
        )
        assert record["action"] == "service.updated"
        assert record["before_state"] is not None
        assert record["after_state"] is not None

    async def test_service_delete_audit(
        self, asyncpg_pool, audit_service, audit_clean
    ):
        record = await assert_audit_record_created(
            asyncpg_pool,
            lambda: audit_service.log_mutation(
                actor_id=uuid.uuid4(),
                actor_role="tech_lead",
                action="service.deleted",
                resource_type="services",
                resource_id=uuid.uuid4(),
                before_state={"name": "svc-alpha"},
                after_state=None,
            ),
        )
        assert record["action"] == "service.deleted"
        assert record["after_state"] is None


# ---------------------------------------------------------------------------
# 3. Policy CRUD audit completeness (AC1)
# ---------------------------------------------------------------------------


class TestPolicyCRUDAuditCompleteness:
    """AC1: policy create/update/delete each produce exactly one audit record."""

    async def test_policy_create_audit(
        self, asyncpg_pool, audit_service, audit_clean
    ):
        record = await assert_audit_record_created(
            asyncpg_pool,
            lambda: audit_service.log_mutation(
                actor_id=uuid.uuid4(),
                actor_role="tech_lead",
                action="policy.created",
                resource_type="policies",
                resource_id=uuid.uuid4(),
                before_state=None,
                after_state={"name": "sec-policy", "dimension": "security"},
            ),
        )
        assert record["action"] == "policy.created"
        assert record["resource_type"] == "policies"
        assert record["before_state"] is None

    async def test_policy_update_audit_captures_state_diff(
        self, asyncpg_pool, audit_service, audit_clean
    ):
        """AC3: before_state and after_state differ in update events."""
        record = await assert_audit_record_created(
            asyncpg_pool,
            lambda: audit_service.log_mutation(
                actor_id=uuid.uuid4(),
                actor_role="tech_lead",
                action="policy.updated",
                resource_type="policies",
                resource_id=uuid.uuid4(),
                before_state={"name": "pol-1", "is_active": True},
                after_state={"name": "pol-1", "is_active": False},
            ),
        )
        assert record["action"] == "policy.updated"
        assert record["before_state"]["is_active"] is True
        assert record["after_state"]["is_active"] is False

    async def test_policy_delete_audit(
        self, asyncpg_pool, audit_service, audit_clean
    ):
        record = await assert_audit_record_created(
            asyncpg_pool,
            lambda: audit_service.log_mutation(
                actor_id=uuid.uuid4(),
                actor_role="tech_lead",
                action="policy.deleted",
                resource_type="policies",
                resource_id=uuid.uuid4(),
                before_state={"name": "pol-1", "dimension": "code_quality"},
                after_state=None,
            ),
        )
        assert record["action"] == "policy.deleted"
        assert record["after_state"] is None


# ---------------------------------------------------------------------------
# 4. Assessment lifecycle audit completeness (AC1)
# ---------------------------------------------------------------------------


class TestAssessmentLifecycleAuditCompleteness:
    """AC1: assessment creation and completion each produce one audit record."""

    async def test_health_assessment_create_audit(
        self, asyncpg_pool, audit_service, audit_clean
    ):
        record = await assert_audit_record_created(
            asyncpg_pool,
            lambda: audit_service.log_event(
                actor_id=uuid.uuid4(),
                actor_role="developer",
                action="assessment.created",
                resource_type="assessments",
                resource_id=uuid.uuid4(),
                before_state=None,
                after_state={"assessment_type": "health_check", "status": "pending"},
            ),
        )
        assert record["action"] == "assessment.created"
        assert record["after_state"]["assessment_type"] == "health_check"

    async def test_release_assessment_create_audit(
        self, asyncpg_pool, audit_service, audit_clean
    ):
        record = await assert_audit_record_created(
            asyncpg_pool,
            lambda: audit_service.log_event(
                actor_id=uuid.uuid4(),
                actor_role="developer",
                action="assessment.created",
                resource_type="assessments",
                resource_id=uuid.uuid4(),
                before_state=None,
                after_state={
                    "assessment_type": "release_readiness",
                    "status": "pending",
                },
            ),
        )
        assert record["after_state"]["assessment_type"] == "release_readiness"

    async def test_assessment_completed_audit(
        self, asyncpg_pool, audit_service, audit_clean
    ):
        record = await assert_audit_record_created(
            asyncpg_pool,
            lambda: audit_service.log_event(
                actor_id=None,
                actor_role="system",
                action="assessment.completed",
                resource_type="assessments",
                resource_id=uuid.uuid4(),
                before_state={"status": "running"},
                after_state={"status": "completed", "score": 85},
            ),
        )
        assert record["action"] == "assessment.completed"
        assert record["actor_id"] is None
        assert record["actor_role"] == "system"


# ---------------------------------------------------------------------------
# 5. Decision action audit completeness (AC1)
# ---------------------------------------------------------------------------


class TestDecisionActionAuditCompleteness:
    """AC1: release approve/block each produce exactly one audit record."""

    async def test_release_approve_audit(
        self, asyncpg_pool, audit_service, audit_clean
    ):
        release_id = uuid.uuid4()
        record = await assert_audit_record_created(
            asyncpg_pool,
            lambda: audit_service.log_event(
                actor_id=uuid.uuid4(),
                actor_role="tech_lead",
                action="release.approve",
                resource_type="releases",
                resource_id=release_id,
                before_state={"status": "pending"},
                after_state={"status": "approved", "decision": "approved"},
            ),
        )
        assert record["action"] == "release.approve"
        assert record["resource_type"] == "releases"
        assert record["resource_id"] == release_id
        assert record["after_state"]["status"] == "approved"

    async def test_release_block_audit(
        self, asyncpg_pool, audit_service, audit_clean
    ):
        record = await assert_audit_record_created(
            asyncpg_pool,
            lambda: audit_service.log_event(
                actor_id=uuid.uuid4(),
                actor_role="tech_lead",
                action="release.block",
                resource_type="releases",
                resource_id=uuid.uuid4(),
                before_state={"status": "pending"},
                after_state={"status": "blocked", "reason": "high risk score"},
            ),
        )
        assert record["action"] == "release.block"
        assert record["after_state"]["status"] == "blocked"


# ---------------------------------------------------------------------------
# 6. Exception lifecycle audit completeness (AC1)
# ---------------------------------------------------------------------------


class TestExceptionLifecycleAuditCompleteness:
    """AC1: exception create and approve each produce one audit record."""

    async def test_exception_created_audit(
        self, asyncpg_pool, audit_service, audit_clean
    ):
        record = await assert_audit_record_created(
            asyncpg_pool,
            lambda: audit_service.log_event(
                actor_id=uuid.uuid4(),
                actor_role="developer",
                action="exception.created",
                resource_type="exceptions",
                resource_id=uuid.uuid4(),
                before_state=None,
                after_state={"reason": "approved-vendor-vuln", "status": "pending"},
            ),
        )
        assert record["action"] == "exception.created"
        assert record["before_state"] is None

    async def test_exception_approved_audit(
        self, asyncpg_pool, audit_service, audit_clean
    ):
        record = await assert_audit_record_created(
            asyncpg_pool,
            lambda: audit_service.log_event(
                actor_id=uuid.uuid4(),
                actor_role="tech_lead",
                action="exception.approved",
                resource_type="exceptions",
                resource_id=uuid.uuid4(),
                before_state={"status": "pending"},
                after_state={"status": "approved"},
            ),
        )
        assert record["action"] == "exception.approved"
        assert record["before_state"]["status"] == "pending"
        assert record["after_state"]["status"] == "approved"


# ---------------------------------------------------------------------------
# 7. RBAC change audit completeness (AC1)
# ---------------------------------------------------------------------------


class TestRBACChangeAuditCompleteness:
    """AC1: role assignment produces one audit record with before/after state."""

    async def test_role_assignment_audit(
        self, asyncpg_pool, audit_service, audit_clean
    ):
        user_id = uuid.uuid4()
        record = await assert_audit_record_created(
            asyncpg_pool,
            lambda: audit_service.log_event(
                actor_id=uuid.uuid4(),
                actor_role="platform_admin",
                action="user.role_assigned",
                resource_type="users",
                resource_id=user_id,
                before_state={"role": "developer"},
                after_state={"role": "tech_lead"},
            ),
        )
        assert record["action"] == "user.role_assigned"
        assert record["resource_type"] == "users"
        assert record["resource_id"] == user_id

    async def test_role_change_captures_both_states(
        self, asyncpg_pool, audit_service, audit_clean
    ):
        """AC3: before_state and after_state differ in role change events."""
        record = await assert_audit_record_created(
            asyncpg_pool,
            lambda: audit_service.log_event(
                actor_id=uuid.uuid4(),
                actor_role="platform_admin",
                action="user.role_assigned",
                resource_type="users",
                resource_id=uuid.uuid4(),
                before_state={"role": "developer", "email": "user@example.com"},
                after_state={"role": "platform_admin", "email": "user@example.com"},
            ),
        )
        assert record["before_state"] != record["after_state"]
        assert record["before_state"]["role"] != record["after_state"]["role"]


# ---------------------------------------------------------------------------
# 8. Authentication event audit completeness (AC4)
# ---------------------------------------------------------------------------


class TestAuthEventAuditCompleteness:
    """AC4: auth events (login, failure, logout, refresh) produce audit records."""

    async def test_login_success_audit(
        self, asyncpg_pool, audit_service, audit_clean
    ):
        user_id = uuid.uuid4()
        record = await assert_audit_record_created(
            asyncpg_pool,
            lambda: audit_service.log_event(
                actor_id=user_id,
                actor_role="developer",
                action="auth.login",
                resource_type="auth",
                resource_id=user_id,
                before_state=None,
                after_state={"status": "success"},
                ip_address="10.0.0.1",
            ),
        )
        assert record["action"] == "auth.login"
        assert record["actor_id"] == user_id
        assert record["after_state"]["status"] == "success"

    async def test_login_failure_audit(
        self, asyncpg_pool, audit_service, audit_clean
    ):
        record = await assert_audit_record_created(
            asyncpg_pool,
            lambda: audit_service.log_event(
                actor_id=None,
                actor_role="anonymous",
                action="auth.login_failed",
                resource_type="auth",
                resource_id=None,
                before_state=None,
                after_state={"reason": "invalid_credentials"},
                ip_address="10.0.0.2",
            ),
        )
        assert record["action"] == "auth.login_failed"
        assert record["actor_id"] is None

    async def test_logout_audit(
        self, asyncpg_pool, audit_service, audit_clean
    ):
        user_id = uuid.uuid4()
        record = await assert_audit_record_created(
            asyncpg_pool,
            lambda: audit_service.log_event(
                actor_id=user_id,
                actor_role="developer",
                action="auth.logout",
                resource_type="auth",
                resource_id=user_id,
                before_state=None,
                after_state={"status": "logged_out"},
            ),
        )
        assert record["action"] == "auth.logout"
        assert record["actor_id"] == user_id

    async def test_token_refresh_audit(
        self, asyncpg_pool, audit_service, audit_clean
    ):
        user_id = uuid.uuid4()
        record = await assert_audit_record_created(
            asyncpg_pool,
            lambda: audit_service.log_event(
                actor_id=user_id,
                actor_role="developer",
                action="auth.token_refresh",
                resource_type="auth",
                resource_id=user_id,
                before_state=None,
                after_state={"status": "refreshed"},
            ),
        )
        assert record["action"] == "auth.token_refresh"


# ---------------------------------------------------------------------------
# 9. Completeness ratio — N mutations → exactly N records (AC6)
# ---------------------------------------------------------------------------


class TestAuditCompletenessRatio:
    """AC6: N diverse mutations produce exactly N audit records (1:1 ratio)."""

    async def test_ten_diverse_mutations_produce_ten_records(
        self, asyncpg_pool, audit_service, audit_clean
    ):
        mutations = [
            {"action": "service.created", "resource_type": "services"},
            {"action": "service.updated", "resource_type": "services"},
            {"action": "service.deleted", "resource_type": "services"},
            {"action": "policy.created", "resource_type": "policies"},
            {"action": "policy.updated", "resource_type": "policies"},
            {"action": "policy.deleted", "resource_type": "policies"},
            {"action": "assessment.created", "resource_type": "assessments"},
            {"action": "release.approve", "resource_type": "releases"},
            {"action": "exception.created", "resource_type": "exceptions"},
            {"action": "auth.login", "resource_type": "auth"},
        ]

        async with asyncpg_pool.acquire() as conn:
            count_before: int = await conn.fetchval("SELECT COUNT(*) FROM audit_logs")

        for m in mutations:
            await audit_service.log_event(
                actor_id=uuid.uuid4(),
                actor_role="developer",
                action=m["action"],
                resource_type=m["resource_type"],
                resource_id=uuid.uuid4(),
            )

        async with asyncpg_pool.acquire() as conn:
            count_after: int = await conn.fetchval("SELECT COUNT(*) FROM audit_logs")

        created = count_after - count_before
        assert created == len(mutations), (
            f"Expected exactly {len(mutations)} audit records; found {created}"
        )

    async def test_each_sequential_write_produces_exactly_one_record(
        self, asyncpg_pool, audit_service, audit_clean
    ):
        """Each log_event call produces exactly one record — no batching or skips."""
        for i in range(5):
            async with asyncpg_pool.acquire() as conn:
                before: int = await conn.fetchval("SELECT COUNT(*) FROM audit_logs")

            await audit_service.log_event(
                actor_id=uuid.uuid4(),
                actor_role="developer",
                action=f"test.event_{i}",
                resource_type="test_resource",
                resource_id=uuid.uuid4(),
            )

            async with asyncpg_pool.acquire() as conn:
                after: int = await conn.fetchval("SELECT COUNT(*) FROM audit_logs")

            assert after - before == 1, (
                f"Write {i}: expected exactly 1 new record, got {after - before}"
            )


# ---------------------------------------------------------------------------
# 10. Correlation ID verification (AC2)
# ---------------------------------------------------------------------------


class TestCorrelationIDVerification:
    """AC2: correlation_id in audit record matches the value passed to log_event."""

    async def test_correlation_id_stored_verbatim(
        self, asyncpg_pool, audit_service, audit_clean
    ):
        correlation_id = str(uuid.uuid4())
        record = await assert_audit_record_created(
            asyncpg_pool,
            lambda: audit_service.log_event(
                actor_id=uuid.uuid4(),
                actor_role="developer",
                action="service.created",
                resource_type="services",
                resource_id=uuid.uuid4(),
                correlation_id=correlation_id,
            ),
        )
        assert record["correlation_id"] == correlation_id, (
            f"Expected correlation_id={correlation_id!r}, "
            f"got {record['correlation_id']!r}"
        )

    async def test_correlation_id_truncated_to_36_chars(
        self, asyncpg_pool, audit_service, audit_clean
    ):
        """AuditService truncates correlation_id to 36 chars (UUID length)."""
        long_id = "x" * 100
        record = await assert_audit_record_created(
            asyncpg_pool,
            lambda: audit_service.log_event(
                actor_id=uuid.uuid4(),
                actor_role="developer",
                action="service.created",
                resource_type="services",
                resource_id=uuid.uuid4(),
                correlation_id=long_id,
            ),
        )
        assert record["correlation_id"] is not None
        assert len(record["correlation_id"]) <= 36

    async def test_none_correlation_id_stored_as_null(
        self, asyncpg_pool, audit_service, audit_clean
    ):
        record = await assert_audit_record_created(
            asyncpg_pool,
            lambda: audit_service.log_event(
                actor_id=uuid.uuid4(),
                actor_role="developer",
                action="service.created",
                resource_type="services",
                resource_id=uuid.uuid4(),
                correlation_id=None,
            ),
        )
        assert record["correlation_id"] is None

    async def test_invalid_actor_id_does_not_prevent_write(
        self, asyncpg_pool, audit_service, audit_clean
    ):
        """Edge case: invalid actor_id is gracefully handled; record still written."""
        async with asyncpg_pool.acquire() as conn:
            count_before: int = await conn.fetchval("SELECT COUNT(*) FROM audit_logs")

        await audit_service.log_event(
            actor_id="not-a-valid-uuid",
            actor_role="developer",
            action="service.created",
            resource_type="services",
            resource_id=uuid.uuid4(),
        )

        async with asyncpg_pool.acquire() as conn:
            count_after: int = await conn.fetchval("SELECT COUNT(*) FROM audit_logs")

        assert count_after == count_before + 1, (
            "AuditService must still write a record when actor_id is invalid "
            "(graceful degradation: actor_id stored as NULL)"
        )
