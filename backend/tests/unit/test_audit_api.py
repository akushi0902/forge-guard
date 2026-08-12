"""Unit tests for the Audit Log Query API (WO-031).

Coverage:
  - AuditLogFilters schema validation (valid inputs, boundary values, bad UUID,
    negative limit, over-max limit)
  - AuditLogListDataResponse / AuditLogDataResponse serialisation
  - PaginationMeta fields
  - Cursor encode/decode round-trip (utils/pagination.py)
  - Cursor decode raises BadRequestError on malformed/corrupted input
  - RBAC dependency rejects non-Platform-Admin roles with 403
  - _require_audit_view allows platform_admin, denies all other roles
"""

from __future__ import annotations

import base64
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from forgeguard.api.schemas.audit import (
    AuditLogDataResponse,
    AuditLogEntry,
    AuditLogFilters,
    AuditLogListDataResponse,
    PaginationMeta,
)
from forgeguard.core.exceptions import BadRequestError, ForbiddenError
from forgeguard.core.permissions import Permissions, UserRole
from forgeguard.utils.pagination import decode_cursor, encode_cursor


# ---------------------------------------------------------------------------
# AuditLogFilters schema validation
# ---------------------------------------------------------------------------

class TestAuditLogFilters:
    def test_defaults(self):
        f = AuditLogFilters()
        assert f.actor_id is None
        assert f.resource_type is None
        assert f.resource_id is None
        assert f.action is None
        assert f.date_from is None
        assert f.date_to is None
        assert f.cursor is None
        assert f.limit == 50

    def test_limit_minimum(self):
        f = AuditLogFilters(limit=1)
        assert f.limit == 1

    def test_limit_maximum(self):
        f = AuditLogFilters(limit=100)
        assert f.limit == 100

    def test_limit_below_minimum_rejected(self):
        with pytest.raises(Exception):
            AuditLogFilters(limit=0)

    def test_limit_above_maximum_rejected(self):
        with pytest.raises(Exception):
            AuditLogFilters(limit=101)

    def test_valid_actor_id(self):
        uid = uuid.uuid4()
        f = AuditLogFilters(actor_id=uid)
        assert f.actor_id == uid

    def test_bad_actor_id_string(self):
        with pytest.raises(Exception):
            AuditLogFilters(actor_id="not-a-uuid")

    def test_valid_date_from(self):
        dt = datetime(2026, 1, 1, tzinfo=timezone.utc)
        f = AuditLogFilters(date_from=dt)
        assert f.date_from == dt

    def test_all_fields_populated(self):
        actor = uuid.uuid4()
        resource = uuid.uuid4()
        now = datetime.now(tz=timezone.utc)
        f = AuditLogFilters(
            actor_id=actor,
            resource_type="users",
            resource_id=resource,
            action="auth.login",
            date_from=now - timedelta(days=30),
            date_to=now,
            cursor="abc123",
            limit=25,
        )
        assert f.actor_id == actor
        assert f.resource_id == resource
        assert f.action == "auth.login"
        assert f.limit == 25


# ---------------------------------------------------------------------------
# PaginationMeta
# ---------------------------------------------------------------------------

class TestPaginationMeta:
    def test_no_more_pages(self):
        meta = PaginationMeta(cursor=None, has_more=False, total_estimate=5)
        assert meta.cursor is None
        assert not meta.has_more
        assert meta.total_estimate == 5

    def test_with_cursor(self):
        meta = PaginationMeta(cursor="abc123", has_more=True, total_estimate=200)
        assert meta.cursor == "abc123"
        assert meta.has_more


# ---------------------------------------------------------------------------
# AuditLogListDataResponse / AuditLogDataResponse serialisation
# ---------------------------------------------------------------------------

def _sample_entry() -> AuditLogEntry:
    return AuditLogEntry(
        id=uuid.uuid4(),
        actor_id=uuid.uuid4(),
        actor_role="developer",
        action="auth.login",
        resource_type="users",
        resource_id=uuid.uuid4(),
        before_state=None,
        after_state={"result": "success"},
        ip_address_masked="192.168.xxx.xxx",
        correlation_id=str(uuid.uuid4()),
        created_at=datetime.now(tz=timezone.utc),
    )


class TestAuditLogResponseModels:
    def test_list_response_empty(self):
        resp = AuditLogListDataResponse(
            data=[],
            pagination=PaginationMeta(cursor=None, has_more=False, total_estimate=0),
        )
        assert resp.data == []
        assert not resp.pagination.has_more
        assert resp.pagination.total_estimate == 0

    def test_list_response_with_entries(self):
        entries = [_sample_entry() for _ in range(3)]
        resp = AuditLogListDataResponse(
            data=entries,
            pagination=PaginationMeta(cursor="next_page", has_more=True, total_estimate=50),
        )
        assert len(resp.data) == 3
        assert resp.pagination.has_more

    def test_single_response(self):
        entry = _sample_entry()
        resp = AuditLogDataResponse(data=entry)
        assert resp.data.action == "auth.login"
        assert resp.data.actor_role == "developer"

    def test_round_trip_serialisation(self):
        entry = _sample_entry()
        resp = AuditLogDataResponse(data=entry)
        dumped = resp.model_dump()
        assert "data" in dumped
        assert dumped["data"]["action"] == "auth.login"


# ---------------------------------------------------------------------------
# Cursor encode/decode utilities
# ---------------------------------------------------------------------------

class TestCursorRoundTrip:
    def test_encode_decode_round_trip(self):
        ts = datetime(2026, 3, 15, 12, 30, 0, tzinfo=timezone.utc)
        record_id = uuid.uuid4()
        cursor = encode_cursor(ts, record_id)
        decoded_ts, decoded_id = decode_cursor(cursor)
        assert decoded_id == record_id
        assert decoded_ts == ts

    def test_cursor_is_base64_string(self):
        ts = datetime.now(tz=timezone.utc)
        cursor = encode_cursor(ts, uuid.uuid4())
        # Must be decodable as base64
        base64.b64decode(cursor.encode())

    def test_different_inputs_produce_different_cursors(self):
        ts1 = datetime(2026, 1, 1, tzinfo=timezone.utc)
        ts2 = datetime(2026, 1, 2, tzinfo=timezone.utc)
        uid = uuid.uuid4()
        assert encode_cursor(ts1, uid) != encode_cursor(ts2, uid)

    def test_naive_datetime_gets_utc_on_decode(self):
        # Encode a UTC-aware datetime; decode should also be UTC-aware.
        ts = datetime(2026, 6, 1, 10, 0, 0, tzinfo=timezone.utc)
        cursor = encode_cursor(ts, uuid.uuid4())
        decoded_ts, _ = decode_cursor(cursor)
        assert decoded_ts.tzinfo is not None

    def test_decode_empty_string_raises(self):
        with pytest.raises(BadRequestError):
            decode_cursor("")

    def test_decode_garbage_raises(self):
        with pytest.raises(BadRequestError):
            decode_cursor("not-valid-base64!!!")

    def test_decode_truncated_raises(self):
        # Valid base64 but missing the | separator
        bad = base64.b64encode(b"2026-01-01T00:00:00").decode()
        with pytest.raises(BadRequestError):
            decode_cursor(bad)

    def test_decode_invalid_uuid_raises(self):
        # Valid base64 with | but non-UUID part
        bad = base64.b64encode(b"2026-01-01T00:00:00+00:00|not-a-uuid").decode()
        with pytest.raises(BadRequestError):
            decode_cursor(bad)


# ---------------------------------------------------------------------------
# RBAC: _require_audit_view dependency
# ---------------------------------------------------------------------------

class TestRequireAuditView:
    """Verify the _require_audit_view dependency allows/denies correctly."""

    @pytest.fixture
    def _dep(self):
        from forgeguard.api.routes.audit import _require_audit_view  # noqa: PLC0415
        return _require_audit_view

    def _make_user(self, role: str):
        from forgeguard.api.dependencies.auth import CurrentUser  # noqa: PLC0415
        return CurrentUser(user_id=uuid.uuid4(), role=role)

    @pytest.mark.asyncio
    async def test_platform_admin_allowed(self, _dep):
        user = self._make_user(UserRole.platform_admin.value)
        result = await _dep(user)
        assert result == user

    @pytest.mark.asyncio
    async def test_developer_denied(self, _dep):
        user = self._make_user(UserRole.developer.value)
        with pytest.raises(ForbiddenError) as exc_info:
            await _dep(user)
        assert Permissions.AUDIT_VIEW in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_security_reviewer_denied(self, _dep):
        user = self._make_user(UserRole.security_reviewer.value)
        with pytest.raises(ForbiddenError):
            await _dep(user)

    @pytest.mark.asyncio
    async def test_tech_lead_denied(self, _dep):
        user = self._make_user(UserRole.tech_lead.value)
        with pytest.raises(ForbiddenError):
            await _dep(user)

    @pytest.mark.asyncio
    async def test_operator_denied(self, _dep):
        user = self._make_user(UserRole.operator.value)
        with pytest.raises(ForbiddenError):
            await _dep(user)

    @pytest.mark.asyncio
    async def test_forbidden_error_message_mentions_platform_admin(self, _dep):
        user = self._make_user(UserRole.developer.value)
        with pytest.raises(ForbiddenError) as exc_info:
            await _dep(user)
        assert "Platform Admin" in exc_info.value.message
