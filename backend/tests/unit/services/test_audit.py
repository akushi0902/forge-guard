"""Unit tests for AuditService, AuditLogRepository, and IP masking (WO-037).

Covers:
  - AuditService.log_event: correct record structure for each action type
  - AuditService.log_mutation: convenience wrapper parity
  - IP masking: IPv4, IPv6, edge cases
  - AuditLogRepository.update/soft_delete raise NotImplementedError (immutability)
  - AuditLogRepository.list_by_resource / list_by_actor method signatures
  - JSONB truncation on oversized payloads
  - PolicyGuardianService audit integration (version increment)

Run:
    pytest tests/unit/services/test_audit.py -v
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from forgeguard.core.ip_masking import mask_ip_address
from forgeguard.services.audit import (
    SYSTEM_ACTOR_ROLE,
    AuditService,
    _truncate_jsonb,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_repo_mock(return_value: dict | None = None) -> MagicMock:
    repo = MagicMock()
    record = return_value or {
        "id": str(uuid.uuid4()),
        "actor_id": str(uuid.uuid4()),
        "actor_role": "developer",
        "action": "policy.created",
        "resource_type": "policy",
        "resource_id": str(uuid.uuid4()),
        "before_state": None,
        "after_state": {"name": "Test Policy"},
        "ip_address_masked": "10.0.0.xxx",
        "correlation_id": str(uuid.uuid4()),
        "created_at": datetime.now(tz=timezone.utc),
    }
    repo.insert = AsyncMock(return_value=record)
    repo.list_by_resource = AsyncMock(return_value=[record])
    repo.list_by_actor = AsyncMock(return_value=[record])
    return repo


# ===========================================================================
# IP Masking
# ===========================================================================

class TestMaskIpAddress:
    def test_ipv4_masks_last_octet(self):
        assert mask_ip_address("192.168.1.100") == "192.168.1.xxx"

    def test_ipv4_preserves_first_three_octets(self):
        result = mask_ip_address("10.20.30.40")
        assert result.startswith("10.20.30.")
        assert result.endswith("xxx")

    def test_ipv4_loopback(self):
        assert mask_ip_address("127.0.0.1") == "127.0.0.xxx"

    def test_ipv6_full_form_masks_last_four_groups(self):
        result = mask_ip_address("2001:0db8:85a3:0000:0000:8a2e:0370:7334")
        assert result.startswith("2001:0db8:85a3:0000:")
        assert "xxxx" in result

    def test_ipv6_shorthand_returns_masked(self):
        assert mask_ip_address("::1") == "masked"
        assert mask_ip_address("2001:db8::1") == "masked"

    def test_none_returns_unknown(self):
        assert mask_ip_address(None) == "unknown"

    def test_empty_string_returns_unknown(self):
        assert mask_ip_address("") == "unknown"

    def test_unrecognised_format_returns_masked(self):
        assert mask_ip_address("not.an.ip") == "masked"

    def test_idempotent_on_already_masked(self):
        already_masked = "192.168.1.xxx"
        result = mask_ip_address(already_masked)
        assert result == "masked"

    def test_whitespace_only_returns_unknown(self):
        assert mask_ip_address("   ") == "unknown"


# ===========================================================================
# _truncate_jsonb helper
# ===========================================================================

class TestTruncateJsonb:
    def test_none_passthrough(self):
        assert _truncate_jsonb(None) is None

    def test_small_dict_unchanged(self):
        d = {"key": "value"}
        assert _truncate_jsonb(d) == d

    def test_large_dict_gets_truncated_marker(self):
        big = {"x": "a" * (1024 * 1024 + 1)}
        result = _truncate_jsonb(big)
        assert result is not None
        assert result.get("__truncated__") is True
        assert "size_bytes" in result

    def test_unserializable_returns_marker(self):
        result = _truncate_jsonb({"obj": object()})  # type: ignore[arg-type]
        assert result is not None
        assert "__unserializable__" in result or "__truncated__" in result


# ===========================================================================
# AuditService.log_event
# ===========================================================================

class TestAuditServiceLogEvent:
    @pytest.mark.asyncio
    async def test_basic_event_structure(self):
        repo = _make_repo_mock()
        svc = AuditService(repo)
        actor_id = uuid.uuid4()
        resource_id = uuid.uuid4()

        await svc.log_event(
            actor_id=actor_id,
            actor_role="developer",
            action="policy.created",
            resource_type="policy",
            resource_id=resource_id,
            after_state={"name": "Test Policy", "version": 1},
        )

        repo.insert.assert_awaited_once()
        record = repo.insert.call_args[0][0]
        assert record["actor_id"] == actor_id
        assert record["actor_role"] == "developer"
        assert record["action"] == "policy.created"
        assert record["resource_type"] == "policy"
        assert record["resource_id"] == resource_id

    @pytest.mark.asyncio
    async def test_before_state_null_for_creates(self):
        repo = _make_repo_mock()
        svc = AuditService(repo)

        await svc.log_event(
            actor_id=uuid.uuid4(),
            actor_role="platform_admin",
            action="policy.created",
            resource_type="policy",
            resource_id=uuid.uuid4(),
            before_state=None,
            after_state={"name": "New Policy"},
        )

        record = repo.insert.call_args[0][0]
        assert record["before_state"] is None

    @pytest.mark.asyncio
    async def test_before_and_after_state_for_updates(self):
        repo = _make_repo_mock()
        svc = AuditService(repo)

        await svc.log_event(
            actor_id=uuid.uuid4(),
            actor_role="platform_admin",
            action="policy.updated",
            resource_type="policy",
            resource_id=uuid.uuid4(),
            before_state={"name": "Old Name", "version": 1},
            after_state={"name": "New Name", "version": 2},
        )

        record = repo.insert.call_args[0][0]
        assert record["before_state"]["name"] == "Old Name"
        assert record["after_state"]["name"] == "New Name"

    @pytest.mark.asyncio
    async def test_ip_address_is_masked(self):
        repo = _make_repo_mock()
        svc = AuditService(repo)

        await svc.log_event(
            actor_id=uuid.uuid4(),
            actor_role="developer",
            action="service.created",
            resource_type="services",
            resource_id=uuid.uuid4(),
            after_state={},
            ip_address="192.168.1.55",
        )

        record = repo.insert.call_args[0][0]
        assert record["ip_address_masked"] == "192.168.1.xxx"
        assert "55" not in record["ip_address_masked"]

    @pytest.mark.asyncio
    async def test_none_ip_stored_as_none(self):
        repo = _make_repo_mock()
        svc = AuditService(repo)

        await svc.log_event(
            actor_id=uuid.uuid4(),
            actor_role="developer",
            action="service.created",
            resource_type="services",
            resource_id=uuid.uuid4(),
            after_state={},
            ip_address=None,
        )

        record = repo.insert.call_args[0][0]
        assert record["ip_address_masked"] is None

    @pytest.mark.asyncio
    async def test_none_actor_id_stored_as_none(self):
        repo = _make_repo_mock()
        svc = AuditService(repo)

        await svc.log_event(
            actor_id=None,
            actor_role=SYSTEM_ACTOR_ROLE,
            action="partition.created",
            resource_type="audit_logs",
            after_state={"partition": "2026_01"},
        )

        record = repo.insert.call_args[0][0]
        assert record["actor_id"] is None
        assert record["actor_role"] == "system"

    @pytest.mark.asyncio
    async def test_correlation_id_stored(self):
        repo = _make_repo_mock()
        svc = AuditService(repo)
        corr_id = str(uuid.uuid4())

        await svc.log_event(
            actor_id=uuid.uuid4(),
            actor_role="developer",
            action="policy.created",
            resource_type="policy",
            resource_id=uuid.uuid4(),
            after_state={},
            correlation_id=corr_id,
        )

        record = repo.insert.call_args[0][0]
        assert record["correlation_id"] == corr_id

    @pytest.mark.asyncio
    async def test_db_error_propagated(self):
        repo = _make_repo_mock()
        repo.insert = AsyncMock(side_effect=RuntimeError("DB down"))
        svc = AuditService(repo)

        with pytest.raises(RuntimeError, match="DB down"):
            await svc.log_event(
                actor_id=uuid.uuid4(),
                actor_role="developer",
                action="policy.created",
                resource_type="policy",
                after_state={},
            )

    @pytest.mark.asyncio
    async def test_invalid_actor_id_string_stored_as_none(self):
        repo = _make_repo_mock()
        svc = AuditService(repo)

        await svc.log_event(
            actor_id="not-a-uuid",
            actor_role="developer",
            action="policy.created",
            resource_type="policy",
            after_state={},
        )

        record = repo.insert.call_args[0][0]
        assert record["actor_id"] is None

    @pytest.mark.asyncio
    async def test_log_mutation_delegates_to_log_event(self):
        repo = _make_repo_mock()
        svc = AuditService(repo)

        result = await svc.log_mutation(
            actor_id=uuid.uuid4(),
            actor_role="platform_admin",
            action="policy.updated",
            resource_type="policy",
            resource_id=uuid.uuid4(),
            before_state={"version": 1},
            after_state={"version": 2},
        )

        assert result is not None
        repo.insert.assert_awaited_once()


# ===========================================================================
# Per-action audit record coverage
# ===========================================================================

@pytest.mark.parametrize("action,resource_type,has_before", [
    ("policy.created", "policy", False),
    ("policy.updated", "policy", True),
    ("policy_rule.created", "policy_rule", False),
    ("policy_rule.updated", "policy_rule", True),
    ("policy_rule.toggled", "policy_rule", True),
])
@pytest.mark.asyncio
async def test_audit_record_per_action_type(action, resource_type, has_before):
    """Each mutation action produces exactly one audit record with correct fields."""
    repo = _make_repo_mock()
    svc = AuditService(repo)

    before = {"name": "before", "version": 1} if has_before else None

    await svc.log_event(
        actor_id=uuid.uuid4(),
        actor_role="platform_admin",
        action=action,
        resource_type=resource_type,
        resource_id=uuid.uuid4(),
        before_state=before,
        after_state={"name": "after", "version": 2},
    )

    repo.insert.assert_awaited_once()
    record = repo.insert.call_args[0][0]
    assert record["action"] == action
    assert record["resource_type"] == resource_type
    if has_before:
        assert record["before_state"] is not None
    else:
        assert record["before_state"] is None


# ===========================================================================
# AuditLogRepository immutability
# ===========================================================================

class TestAuditLogRepositoryImmutability:
    def test_update_raises_not_implemented(self):
        from forgeguard.data.repositories.audit_logs import AuditLogRepository
        repo = AuditLogRepository.__new__(AuditLogRepository)
        with pytest.raises(NotImplementedError, match="immutable"):
            import asyncio
            asyncio.get_event_loop().run_until_complete(
                repo.update(uuid.uuid4(), {})
            )

    def test_soft_delete_raises_not_implemented(self):
        from forgeguard.data.repositories.audit_logs import AuditLogRepository
        repo = AuditLogRepository.__new__(AuditLogRepository)
        with pytest.raises(NotImplementedError, match="immutable"):
            import asyncio
            asyncio.get_event_loop().run_until_complete(
                repo.soft_delete(uuid.uuid4())
            )

    def test_list_by_resource_exists(self):
        from forgeguard.data.repositories.audit_logs import AuditLogRepository
        assert hasattr(AuditLogRepository, "list_by_resource")
        assert callable(AuditLogRepository.list_by_resource)

    def test_list_by_actor_exists(self):
        from forgeguard.data.repositories.audit_logs import AuditLogRepository
        assert hasattr(AuditLogRepository, "list_by_actor")
        assert callable(AuditLogRepository.list_by_actor)


# ===========================================================================
# PolicyGuardianService version increment logic
# ===========================================================================

class TestPolicyGuardianVersionIncrement:
    """Verify that update_policy atomically increments the version column."""

    @pytest.mark.asyncio
    async def test_version_increments_on_update(self):
        from forgeguard.data.repositories.policies import PolicyRepository
        from forgeguard.services.policy_guardian import PolicyGuardianService

        policy_id = uuid.uuid4()
        before_row = {
            "id": policy_id,
            "name": "Original Name",
            "dimension": "security",
            "description": None,
            "is_active": True,
            "version": 1,
            "created_by": None,
            "created_at": datetime.now(tz=timezone.utc),
            "updated_at": datetime.now(tz=timezone.utc),
        }
        after_update = {**before_row, "name": "Updated Name"}
        after_increment = {**after_update, "version": 2}

        repo = MagicMock(spec=PolicyRepository)
        repo.get_by_id = AsyncMock(return_value=before_row)
        repo.update = AsyncMock(return_value=after_update)
        repo.increment_version = AsyncMock(return_value=after_increment)

        audit_svc = MagicMock()
        audit_svc.log_event = AsyncMock()

        svc = PolicyGuardianService(repo, audit_svc)
        result = await svc.update_policy(
            policy_id,
            {"name": "Updated Name"},
            actor_id=str(uuid.uuid4()),
            actor_role="platform_admin",
        )

        assert result["version"] == 2
        repo.increment_version.assert_awaited_once_with(policy_id)

    @pytest.mark.asyncio
    async def test_version_in_audit_after_state(self):
        from forgeguard.data.repositories.policies import PolicyRepository
        from forgeguard.services.policy_guardian import PolicyGuardianService

        policy_id = uuid.uuid4()
        ts = datetime.now(tz=timezone.utc)
        before_row = {
            "id": policy_id, "name": "Old", "dimension": "security",
            "description": None, "is_active": True, "version": 3,
            "created_by": None, "created_at": ts, "updated_at": ts,
        }
        after_row = {**before_row, "name": "New", "version": 4}

        repo = MagicMock(spec=PolicyRepository)
        repo.get_by_id = AsyncMock(return_value=before_row)
        repo.update = AsyncMock(return_value={**before_row, "name": "New"})
        repo.increment_version = AsyncMock(return_value=after_row)

        audit_svc = MagicMock()
        audit_svc.log_event = AsyncMock()

        svc = PolicyGuardianService(repo, audit_svc)
        await svc.update_policy(
            policy_id,
            {"name": "New"},
            actor_id=str(uuid.uuid4()),
            actor_role="platform_admin",
        )

        call_kwargs = audit_svc.log_event.call_args.kwargs
        assert call_kwargs["after_state"]["version"] == 4
        assert call_kwargs["before_state"]["version"] == 3

    @pytest.mark.asyncio
    async def test_version_mismatch_raises_value_error(self):
        from forgeguard.data.repositories.policies import PolicyRepository
        from forgeguard.services.policy_guardian import PolicyGuardianService

        policy_id = uuid.uuid4()
        ts = datetime.now(tz=timezone.utc)
        existing = {
            "id": policy_id, "name": "Test", "dimension": "security",
            "description": None, "is_active": True, "version": 5,
            "created_by": None, "created_at": ts, "updated_at": ts,
        }

        repo = MagicMock(spec=PolicyRepository)
        repo.get_by_id = AsyncMock(return_value=existing)
        repo.update = AsyncMock()
        repo.increment_version = AsyncMock()

        svc = PolicyGuardianService(repo)
        with pytest.raises(ValueError, match="Version mismatch"):
            await svc.update_policy(
                policy_id,
                {"name": "Changed"},
                actor_id=str(uuid.uuid4()),
                actor_role="platform_admin",
                expected_version=3,  # wrong — actual is 5
            )
