"""Unit tests for DataSubjectService (WO-034).

All tests use mock asyncpg pools — no database required.

Scenarios covered:
  access_data:
    - Returns profile dict with counts from mock DB
    - Raises BadRequestError when user not found

  rectify_data:
    - Updates email and/or name, returns updated record
    - Raises BadRequestError when no fields provided
    - Raises ConflictError on duplicate email

  erase_data:
    - Writes erasure audit record, overwrites email/name, revokes tokens
    - Raises ConflictError for last Platform Admin
    - Idempotent when user already deactivated

  export_data:
    - Returns structured dict with profile + empty related lists
    - Raises BadRequestError when user not found
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from forgeguard.core.exceptions import BadRequestError, ConflictError
from forgeguard.services.data_subject import DataSubjectService, _decode_name


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def _make_user_row(**overrides) -> dict:
    defaults = {
        "id": uuid.uuid4(),
        "email": "alice@example.com",
        "name_encrypted": b"Alice",
        "role": "developer",
        "is_active": True,
        "created_at": _utcnow(),
        "updated_at": _utcnow(),
        "deleted_at": None,
    }
    defaults.update(overrides)
    return defaults


def _mock_conn(user_row=None, audit_count=0, assessments_count=0, decisions_count=0,
               *, fetchrow_rows=None):
    """Build a mock asyncpg connection.

    fetchrow_rows: optional list of records returned for successive fetchrow calls.
    """
    conn = AsyncMock()
    conn.__aenter__ = AsyncMock(return_value=conn)
    conn.__aexit__ = AsyncMock(return_value=False)

    if fetchrow_rows is not None:
        conn.fetchrow = AsyncMock(side_effect=fetchrow_rows)
    else:
        conn.fetchrow = AsyncMock(return_value=user_row)

    conn.fetchval = AsyncMock(side_effect=[audit_count, assessments_count, decisions_count])
    conn.fetch = AsyncMock(return_value=[])
    conn.execute = AsyncMock()

    # Transaction context manager
    tx = AsyncMock()
    tx.__aenter__ = AsyncMock(return_value=tx)
    tx.__aexit__ = AsyncMock(return_value=False)
    conn.transaction = MagicMock(return_value=tx)

    return conn


def _mock_pool(conn):
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=conn)
    return pool


def _mock_audit_service(erasure_record_id=None):
    audit = AsyncMock()
    audit.log_event = AsyncMock(return_value={"id": erasure_record_id or uuid.uuid4()})
    audit.log_mutation = AsyncMock(return_value={"id": uuid.uuid4()})
    return audit


# ---------------------------------------------------------------------------
# _decode_name helper
# ---------------------------------------------------------------------------

class TestDecodeName:
    def test_bytes(self):
        assert _decode_name(b"Alice") == "Alice"

    def test_str(self):
        assert _decode_name("Alice") == "Alice"

    def test_none(self):
        assert _decode_name(None) is None

    def test_memoryview(self):
        assert _decode_name(memoryview(b"Bob")) == "Bob"


# ---------------------------------------------------------------------------
# access_data
# ---------------------------------------------------------------------------

class TestAccessData:
    async def test_returns_profile_with_counts(self):
        user = _make_user_row()
        conn = _mock_conn(user_row=user, audit_count=5, assessments_count=2, decisions_count=1)
        pool = _mock_pool(conn)
        svc = DataSubjectService(pool)

        result = await svc.access_data(user["id"])

        assert result["email"] == "alice@example.com"
        assert result["name"] == "Alice"
        assert result["related_records"]["audit_log_count"] == 5
        assert result["related_records"]["assessments_count"] == 2
        assert result["related_records"]["decisions_count"] == 1

    async def test_raises_bad_request_when_user_not_found(self):
        conn = _mock_conn(user_row=None)
        pool = _mock_pool(conn)
        svc = DataSubjectService(pool)

        with pytest.raises(BadRequestError):
            await svc.access_data(uuid.uuid4())

    async def test_logs_audit_when_audit_service_present(self):
        user = _make_user_row()
        conn = _mock_conn(user_row=user, audit_count=0, assessments_count=0, decisions_count=0)
        pool = _mock_pool(conn)
        audit = _mock_audit_service()
        svc = DataSubjectService(pool, audit)

        await svc.access_data(user["id"])

        audit.log_event.assert_called_once()
        call_kwargs = audit.log_event.call_args.kwargs
        assert call_kwargs["action"] == "gdpr.access_data"


# ---------------------------------------------------------------------------
# rectify_data
# ---------------------------------------------------------------------------

class TestRectifyData:
    def _make_updated_row(self, user, email=None, name=None) -> dict:
        row = dict(user)
        if email:
            row["email"] = email
        if name:
            row["name_encrypted"] = name.encode("utf-8")
        row["updated_at"] = _utcnow()
        return row

    async def test_raises_bad_request_when_no_fields(self):
        pool = _mock_pool(AsyncMock())
        svc = DataSubjectService(pool)

        with pytest.raises(BadRequestError, match="At least one field"):
            await svc.rectify_data(uuid.uuid4(), "developer")

    async def test_raises_bad_request_when_user_not_found(self):
        conn = _mock_conn(fetchrow_rows=[None])
        pool = _mock_pool(conn)
        svc = DataSubjectService(pool)

        with pytest.raises(BadRequestError, match="User not found"):
            await svc.rectify_data(uuid.uuid4(), "developer", email="new@example.com")

    async def test_raises_conflict_on_duplicate_email(self):
        user = _make_user_row()
        existing_other = _make_user_row(email="taken@example.com")
        conn = _mock_conn(fetchrow_rows=[user, existing_other])
        pool = _mock_pool(conn)
        svc = DataSubjectService(pool)

        with pytest.raises(ConflictError, match="already in use"):
            await svc.rectify_data(user["id"], "developer", email="taken@example.com")

    async def test_updates_name_only(self):
        user = _make_user_row()
        updated = self._make_updated_row(user, name="Bob")
        # fetchrow called twice: snapshot, then RETURNING row
        conn = _mock_conn(fetchrow_rows=[user, updated])
        pool = _mock_pool(conn)
        svc = DataSubjectService(pool)

        result = await svc.rectify_data(user["id"], "developer", name="Bob")

        assert result["name"] == "Bob"

    async def test_updates_email_when_not_duplicate(self):
        user = _make_user_row()
        updated = self._make_updated_row(user, email="new@example.com")
        # fetchrow: snapshot, uniqueness check → None, RETURNING row
        conn = _mock_conn(fetchrow_rows=[user, None, updated])
        pool = _mock_pool(conn)
        svc = DataSubjectService(pool)

        result = await svc.rectify_data(user["id"], "developer", email="new@example.com")

        assert result["email"] == "new@example.com"


# ---------------------------------------------------------------------------
# erase_data
# ---------------------------------------------------------------------------

class TestEraseData:
    def _make_conn_for_erasure(self, user_row, other_admin_count=1):
        conn = AsyncMock()
        conn.__aenter__ = AsyncMock(return_value=conn)
        conn.__aexit__ = AsyncMock(return_value=False)

        conn.fetchrow = AsyncMock(return_value=user_row)
        conn.fetchval = AsyncMock(return_value=other_admin_count)
        conn.execute = AsyncMock()

        tx = AsyncMock()
        tx.__aenter__ = AsyncMock(return_value=tx)
        tx.__aexit__ = AsyncMock(return_value=False)
        conn.transaction = MagicMock(return_value=tx)

        return conn

    async def test_raises_conflict_for_last_platform_admin(self):
        user = _make_user_row(role="platform_admin")
        conn = self._make_conn_for_erasure(user, other_admin_count=0)
        pool = _mock_pool(conn)
        svc = DataSubjectService(pool)

        with pytest.raises(ConflictError, match="last active Platform Admin"):
            await svc.erase_data(user["id"], "platform_admin")

    async def test_erases_user_and_revokes_tokens(self):
        user = _make_user_row(role="developer")
        conn = self._make_conn_for_erasure(user)
        pool = _mock_pool(conn)
        audit = _mock_audit_service()
        svc = DataSubjectService(pool, audit)

        await svc.erase_data(user["id"], "developer")

        # Should have executed at least 3 SQL statements:
        # - UPDATE users (overwrite PII)
        # - UPDATE audit_logs (anonymize)
        # - UPDATE refresh_tokens (revoke)
        assert conn.execute.call_count >= 3

    async def test_idempotent_when_already_deleted(self):
        user = _make_user_row(deleted_at=_utcnow())
        conn = self._make_conn_for_erasure(user)
        pool = _mock_pool(conn)
        svc = DataSubjectService(pool)

        # Should not raise; returns silently
        await svc.erase_data(user["id"], "developer")

        # No UPDATE should have been executed
        conn.execute.assert_not_called()

    async def test_idempotent_when_already_inactive(self):
        user = _make_user_row(is_active=False, deleted_at=None)
        conn = self._make_conn_for_erasure(user)
        pool = _mock_pool(conn)
        svc = DataSubjectService(pool)

        await svc.erase_data(user["id"], "developer")

        conn.execute.assert_not_called()

    async def test_allows_platform_admin_with_other_admins(self):
        user = _make_user_row(role="platform_admin")
        conn = self._make_conn_for_erasure(user, other_admin_count=2)
        pool = _mock_pool(conn)
        audit = _mock_audit_service()
        svc = DataSubjectService(pool, audit)

        # Should not raise
        await svc.erase_data(user["id"], "platform_admin")

        assert conn.execute.call_count >= 3


# ---------------------------------------------------------------------------
# export_data
# ---------------------------------------------------------------------------

class TestExportData:
    async def test_raises_bad_request_when_user_not_found(self):
        conn = MagicMock()
        conn.__aenter__ = AsyncMock(return_value=conn)
        conn.__aexit__ = AsyncMock(return_value=False)
        conn.fetchrow = AsyncMock(return_value=None)
        pool = _mock_pool(conn)
        svc = DataSubjectService(pool)

        with pytest.raises(BadRequestError, match="User not found"):
            await svc.export_data(uuid.uuid4())

    async def test_returns_structured_export(self):
        user = _make_user_row()
        conn = MagicMock()
        conn.__aenter__ = AsyncMock(return_value=conn)
        conn.__aexit__ = AsyncMock(return_value=False)
        conn.fetchrow = AsyncMock(return_value=user)
        conn.fetch = AsyncMock(return_value=[])
        pool = _mock_pool(conn)
        svc = DataSubjectService(pool)

        result = await svc.export_data(user["id"])

        assert "profile" in result
        assert result["profile"]["email"] == "alice@example.com"
        assert result["profile"]["name"] == "Alice"
        assert isinstance(result["audit_logs"], list)
        assert isinstance(result["assessments"], list)
        assert isinstance(result["decisions"], list)
