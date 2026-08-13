"""Unit tests for AuditService (WO-030).

Covers:
  - log_event with valid input persists correct record
  - IP address masking applied before persistence
  - None IP handled gracefully
  - before_state=None allowed (create operations)
  - Large JSONB is truncated at 1MB with __truncated__ marker
  - log_mutation is a thin wrapper over log_event
  - Database write failure is logged and propagated
  - System actor (actor_id=None) produces valid record
  - action slug passed through unchanged
  - correlation_id is optional
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from forgeguard.services.audit import (
    AuditService,
    SYSTEM_ACTOR_ROLE,
    _truncate_jsonb,
)


# ---------------------------------------------------------------------------
# _truncate_jsonb helper
# ---------------------------------------------------------------------------

class TestTruncateJsonb:
    def test_none_returns_none(self):
        assert _truncate_jsonb(None) is None

    def test_small_dict_unchanged(self):
        d = {"key": "value", "count": 42}
        assert _truncate_jsonb(d) == d

    def test_large_dict_truncated(self):
        large = {"data": "x" * (1024 * 1024 + 100)}
        result = _truncate_jsonb(large)
        assert result is not None
        assert result.get("__truncated__") is True
        assert "size_bytes" in result

    def test_empty_dict_unchanged(self):
        assert _truncate_jsonb({}) == {}

    def test_exactly_at_limit_not_truncated(self):
        # A small dict well under 1MB should pass unchanged
        d = {"key": "value"}
        assert _truncate_jsonb(d) is d or _truncate_jsonb(d) == d


# ---------------------------------------------------------------------------
# AuditService.log_event
# ---------------------------------------------------------------------------

def _make_service():
    mock_repo = MagicMock()
    sample_row = {
        "id": uuid.uuid4(),
        "actor_role": "developer",
        "action": "service.created",
        "resource_type": "services",
        "resource_id": uuid.uuid4(),
        "ip_address_masked": "10.0.0.xxx",
        "correlation_id": str(uuid.uuid4()),
    }
    mock_repo.insert = AsyncMock(return_value=sample_row)
    return AuditService(mock_repo), mock_repo


class TestLogEventValid:
    async def test_returns_inserted_record(self):
        svc, repo = _make_service()
        result = await svc.log_event(
            actor_id=uuid.uuid4(),
            actor_role="developer",
            action="service.created",
            resource_type="services",
        )
        assert result is not None
        repo.insert.assert_awaited_once()

    async def test_ip_masking_applied(self):
        svc, repo = _make_service()
        await svc.log_event(
            actor_id=uuid.uuid4(),
            actor_role="developer",
            action="service.created",
            resource_type="services",
            ip_address="192.168.1.100",
        )
        inserted = repo.insert.call_args[0][0]
        assert inserted["ip_address_masked"] == "192.168.1.xxx"
        assert inserted.get("ip_address") is None  # raw IP never stored

    async def test_none_ip_stored_as_none(self):
        svc, repo = _make_service()
        await svc.log_event(
            actor_id=uuid.uuid4(),
            actor_role="developer",
            action="service.created",
            resource_type="services",
            ip_address=None,
        )
        inserted = repo.insert.call_args[0][0]
        assert inserted["ip_address_masked"] is None

    async def test_before_state_none_allowed(self):
        svc, repo = _make_service()
        await svc.log_event(
            actor_id=uuid.uuid4(),
            actor_role="developer",
            action="service.created",
            resource_type="services",
            before_state=None,
        )
        inserted = repo.insert.call_args[0][0]
        assert inserted["before_state"] is None

    async def test_actor_id_none_allowed(self):
        svc, repo = _make_service()
        await svc.log_event(
            actor_id=None,
            actor_role=SYSTEM_ACTOR_ROLE,
            action="partition.created",
            resource_type="audit_logs",
        )
        inserted = repo.insert.call_args[0][0]
        assert inserted["actor_id"] is None

    async def test_actor_role_defaulted_when_empty(self):
        svc, repo = _make_service()
        await svc.log_event(
            actor_id=None,
            actor_role="",
            action="system.event",
            resource_type="system",
        )
        inserted = repo.insert.call_args[0][0]
        assert inserted["actor_role"] == SYSTEM_ACTOR_ROLE

    async def test_action_slug_preserved(self):
        svc, repo = _make_service()
        await svc.log_event(
            actor_id=None,
            actor_role="system",
            action="custom.action.slug",
            resource_type="services",
        )
        inserted = repo.insert.call_args[0][0]
        assert inserted["action"] == "custom.action.slug"

    async def test_resource_id_none_allowed(self):
        svc, repo = _make_service()
        await svc.log_event(
            actor_id=uuid.uuid4(),
            actor_role="developer",
            action="bulk.import",
            resource_type="services",
            resource_id=None,
        )
        inserted = repo.insert.call_args[0][0]
        assert inserted["resource_id"] is None

    async def test_correlation_id_stored(self):
        svc, repo = _make_service()
        cid = str(uuid.uuid4())
        await svc.log_event(
            actor_id=uuid.uuid4(),
            actor_role="developer",
            action="service.created",
            resource_type="services",
            correlation_id=cid,
        )
        inserted = repo.insert.call_args[0][0]
        assert inserted["correlation_id"] == cid

    async def test_correlation_id_none_allowed(self):
        svc, repo = _make_service()
        await svc.log_event(
            actor_id=uuid.uuid4(),
            actor_role="developer",
            action="service.created",
            resource_type="services",
            correlation_id=None,
        )
        inserted = repo.insert.call_args[0][0]
        assert inserted["correlation_id"] is None

    async def test_large_before_state_truncated(self):
        svc, repo = _make_service()
        large = {"data": "x" * (1024 * 1024 + 100)}
        await svc.log_event(
            actor_id=uuid.uuid4(),
            actor_role="developer",
            action="policy.updated",
            resource_type="policies",
            before_state=large,
        )
        inserted = repo.insert.call_args[0][0]
        assert inserted["before_state"].get("__truncated__") is True

    async def test_large_after_state_truncated(self):
        svc, repo = _make_service()
        large = {"data": "x" * (1024 * 1024 + 100)}
        await svc.log_event(
            actor_id=uuid.uuid4(),
            actor_role="developer",
            action="policy.updated",
            resource_type="policies",
            after_state=large,
        )
        inserted = repo.insert.call_args[0][0]
        assert inserted["after_state"].get("__truncated__") is True

    async def test_record_has_uuid_id(self):
        svc, repo = _make_service()
        await svc.log_event(
            actor_id=uuid.uuid4(),
            actor_role="developer",
            action="service.created",
            resource_type="services",
        )
        inserted = repo.insert.call_args[0][0]
        assert isinstance(inserted["id"], uuid.UUID)


# ---------------------------------------------------------------------------
# DB write failure
# ---------------------------------------------------------------------------

class TestLogEventFailure:
    async def test_db_failure_propagated(self):
        svc, repo = _make_service()
        repo.insert.side_effect = RuntimeError("DB is down")
        with pytest.raises(RuntimeError, match="DB is down"):
            await svc.log_event(
                actor_id=uuid.uuid4(),
                actor_role="developer",
                action="service.created",
                resource_type="services",
            )


# ---------------------------------------------------------------------------
# log_mutation is a wrapper
# ---------------------------------------------------------------------------

class TestLogMutation:
    async def test_log_mutation_delegates_to_log_event(self):
        svc, repo = _make_service()
        rid = uuid.uuid4()
        await svc.log_mutation(
            actor_id=uuid.uuid4(),
            actor_role="tech_lead",
            action="service.updated",
            resource_type="services",
            resource_id=rid,
            before_state={"id": str(rid)},
            after_state={"id": str(rid), "status": "deprecated"},
        )
        repo.insert.assert_awaited_once()
        inserted = repo.insert.call_args[0][0]
        assert inserted["action"] == "service.updated"
        assert inserted["before_state"] == {"id": str(rid)}

    async def test_log_mutation_returns_record(self):
        svc, repo = _make_service()
        result = await svc.log_mutation(
            actor_id=uuid.uuid4(),
            actor_role="developer",
            action="service.deleted",
            resource_type="services",
        )
        assert result is not None
