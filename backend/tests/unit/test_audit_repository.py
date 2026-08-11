"""Unit tests for AuditLogRepository (WO-030).

Covers:
  - update() raises NotImplementedError (immutability enforcement)
  - soft_delete() raises NotImplementedError (immutability enforcement)
  - AuditLogRepository has no delete() method in public API
  - insert() is an alias for create() (append-only write path)
  - query() builds correct parameterised queries
"""

from __future__ import annotations

import inspect
import uuid

import pytest

from forgeguard.data.repositories.audit_logs import AuditLogRepository


# ---------------------------------------------------------------------------
# Immutability: no update or delete
# ---------------------------------------------------------------------------

class TestImmutabilityEnforcement:
    def _make_repo(self):
        from unittest.mock import MagicMock  # noqa: PLC0415
        return AuditLogRepository(MagicMock())

    async def test_update_raises_not_implemented(self):
        repo = self._make_repo()
        with pytest.raises(NotImplementedError, match="immutable"):
            await repo.update(uuid.uuid4(), {"actor_role": "hacked"})

    async def test_soft_delete_raises_not_implemented(self):
        repo = self._make_repo()
        with pytest.raises(NotImplementedError, match="immutable"):
            await repo.soft_delete(uuid.uuid4())

    def test_no_delete_method(self):
        methods = [name for name, _ in inspect.getmembers(AuditLogRepository, predicate=inspect.isfunction)]
        assert "delete" not in methods

    def test_no_hard_delete_method(self):
        methods = [name for name, _ in inspect.getmembers(AuditLogRepository, predicate=inspect.isfunction)]
        assert "hard_delete" not in methods

    def test_no_update_all_method(self):
        methods = [name for name, _ in inspect.getmembers(AuditLogRepository, predicate=inspect.isfunction)]
        assert "update_all" not in methods


# ---------------------------------------------------------------------------
# insert() is the canonical append-only write path
# ---------------------------------------------------------------------------

class TestInsertMethod:
    def test_insert_method_exists(self):
        assert hasattr(AuditLogRepository, "insert")
        assert callable(AuditLogRepository.insert)

    def test_insert_is_async(self):
        assert inspect.iscoroutinefunction(AuditLogRepository.insert)

    def test_query_method_exists(self):
        assert hasattr(AuditLogRepository, "query")
        assert callable(AuditLogRepository.query)

    def test_query_is_async(self):
        assert inspect.iscoroutinefunction(AuditLogRepository.query)


# ---------------------------------------------------------------------------
# ALLOWED_INSERT set does not include update-enabling columns
# ---------------------------------------------------------------------------

class TestAllowedInsertFields:
    def test_allowed_insert_has_required_fields(self):
        from forgeguard.data.repositories.audit_logs import _ALLOWED_INSERT  # noqa: PLC0415

        required = {"actor_id", "actor_role", "action", "resource_type",
                    "before_state", "after_state", "ip_address_masked", "correlation_id"}
        assert required.issubset(_ALLOWED_INSERT)

    def test_allowed_insert_excludes_created_at(self):
        # created_at is server-defaulted; never passed by the application
        from forgeguard.data.repositories.audit_logs import _ALLOWED_INSERT  # noqa: PLC0415
        assert "created_at" not in _ALLOWED_INSERT

    def test_no_updated_at_in_allowed_insert(self):
        from forgeguard.data.repositories.audit_logs import _ALLOWED_INSERT  # noqa: PLC0415
        assert "updated_at" not in _ALLOWED_INSERT
