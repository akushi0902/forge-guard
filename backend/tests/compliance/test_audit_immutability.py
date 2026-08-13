"""Audit log immutability compliance test suite (WO-099).

Verifies that audit_logs records cannot be modified or deleted after creation,
as required by SOC 2 and GDPR.

Immutability is enforced at three independent layers (defence-in-depth):
  1. Application layer: AuditLogRepository.update/soft_delete raise NotImplementedError.
  2. Role layer: forgeguard_app role has INSERT/SELECT only (no UPDATE/DELETE privilege).
  3. Trigger layer: BEFORE UPDATE OR DELETE trigger installed by migration b8c9d0e1f2a3
     raises a PostgreSQL EXCEPTION for any attempt, regardless of the database role.

These tests exercise layer 3 (trigger) and layer 1 (application).

Tests require Docker (PostgreSQL testcontainer) and are tagged integration.

Run:
    pytest tests/compliance/test_audit_immutability.py -v -m integration
"""

from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _insert_audit_record(audit_service, action: str = "service.created") -> dict:
    """Insert one audit record and return it."""
    return await audit_service.log_event(
        actor_id=uuid.uuid4(),
        actor_role="developer",
        action=action,
        resource_type="services",
        resource_id=uuid.uuid4(),
        after_state={"name": "immutability-test-svc"},
    )


# ---------------------------------------------------------------------------
# TestAuditLogImmutability
# ---------------------------------------------------------------------------


class TestAuditLogImmutability:
    """AC5: UPDATE and DELETE on audit_logs raise a database error."""

    async def test_update_raises_postgres_error(
        self, asyncpg_pool, audit_service, audit_clean
    ):
        """Layer 3: trigger rejects UPDATE regardless of database role."""
        import asyncpg  # noqa: PLC0415

        record = await _insert_audit_record(audit_service)
        record_id = record["id"]

        with pytest.raises(asyncpg.exceptions.RaiseError) as exc_info:
            async with asyncpg_pool.acquire() as conn:
                await conn.execute(
                    "UPDATE audit_logs SET action = $1 WHERE id = $2",
                    "tampered.action",
                    record_id,
                )

        assert "immutable" in str(exc_info.value).lower(), (
            "Error message must reference 'immutable': "
            f"got {str(exc_info.value)!r}"
        )

    async def test_delete_raises_postgres_error(
        self, asyncpg_pool, audit_service, audit_clean
    ):
        """Layer 3: trigger rejects DELETE regardless of database role."""
        import asyncpg  # noqa: PLC0415

        record = await _insert_audit_record(audit_service, action="policy.created")
        record_id = record["id"]

        with pytest.raises(asyncpg.exceptions.RaiseError) as exc_info:
            async with asyncpg_pool.acquire() as conn:
                await conn.execute(
                    "DELETE FROM audit_logs WHERE id = $1",
                    record_id,
                )

        assert "immutable" in str(exc_info.value).lower(), (
            "Error message must reference 'immutable': "
            f"got {str(exc_info.value)!r}"
        )

    async def test_record_unchanged_after_failed_update(
        self, asyncpg_pool, audit_service, audit_clean
    ):
        """Original record is preserved — failed UPDATE rolls back completely."""
        import asyncpg  # noqa: PLC0415

        original_action = "service.created"
        record = await _insert_audit_record(audit_service, action=original_action)
        record_id = record["id"]

        with pytest.raises(asyncpg.exceptions.RaiseError):
            async with asyncpg_pool.acquire() as conn:
                await conn.execute(
                    "UPDATE audit_logs SET action = 'tampered' WHERE id = $1",
                    record_id,
                )

        async with asyncpg_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT action FROM audit_logs WHERE id = $1", record_id
            )

        assert row is not None, "Audit record must still exist after failed UPDATE"
        assert row["action"] == original_action, (
            f"action was mutated: expected {original_action!r}, got {row['action']!r}"
        )

    async def test_record_exists_after_failed_delete(
        self, asyncpg_pool, audit_service, audit_clean
    ):
        """Record count is unchanged — failed DELETE rolls back completely."""
        import asyncpg  # noqa: PLC0415

        record = await _insert_audit_record(audit_service, action="exception.created")
        record_id = record["id"]

        with pytest.raises(asyncpg.exceptions.RaiseError):
            async with asyncpg_pool.acquire() as conn:
                await conn.execute(
                    "DELETE FROM audit_logs WHERE id = $1", record_id
                )

        async with asyncpg_pool.acquire() as conn:
            count: int = await conn.fetchval(
                "SELECT COUNT(*) FROM audit_logs WHERE id = $1", record_id
            )

        assert count == 1, (
            f"Record must still exist after rejected DELETE; found {count}"
        )

    async def test_bulk_update_raises_on_first_row(
        self, asyncpg_pool, audit_service, audit_clean
    ):
        """Trigger fires per-row — bulk UPDATE raises on the first row processed."""
        import asyncpg  # noqa: PLC0415

        for action in ("service.created", "policy.created", "auth.login"):
            await _insert_audit_record(audit_service, action=action)

        with pytest.raises(asyncpg.exceptions.RaiseError):
            async with asyncpg_pool.acquire() as conn:
                await conn.execute(
                    "UPDATE audit_logs SET action = 'tampered'"
                )

        async with asyncpg_pool.acquire() as conn:
            count: int = await conn.fetchval(
                "SELECT COUNT(*) FROM audit_logs WHERE action = 'tampered'"
            )

        assert count == 0, (
            "No rows should have been tampered; trigger must have blocked all UPDATEs"
        )

    async def test_application_layer_repository_rejects_update(self):
        """Layer 1: AuditLogRepository.update() raises NotImplementedError."""
        from forgeguard.data.repositories.audit_logs import AuditLogRepository  # noqa: PLC0415

        class _FakePool:
            pass

        repo = AuditLogRepository(pool=_FakePool())  # type: ignore[arg-type]

        with pytest.raises(NotImplementedError, match="immutable"):
            await repo.update(uuid.uuid4(), {"action": "tampered"})

    async def test_application_layer_repository_rejects_soft_delete(self):
        """Layer 1: AuditLogRepository.soft_delete() raises NotImplementedError."""
        from forgeguard.data.repositories.audit_logs import AuditLogRepository  # noqa: PLC0415

        class _FakePool:
            pass

        repo = AuditLogRepository(pool=_FakePool())  # type: ignore[arg-type]

        with pytest.raises(NotImplementedError, match="immutable"):
            await repo.soft_delete(uuid.uuid4())
