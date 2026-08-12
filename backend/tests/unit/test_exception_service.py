"""Unit tests for ExceptionService — validation, routing logic, RBAC (WO-062)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from forgeguard.api.schemas.exception import ExceptionRequest
from forgeguard.core.exceptions import BadRequestError, ConflictError, NotFoundError
from forgeguard.services.remediation.exception_service import (
    ExceptionService,
    _route_approver,
)
from tests.fixtures.exception_fixtures import (
    EXCEPTION_ROW,
    FINDING_CODE_QUALITY_ROW,
    FINDING_DOCUMENTATION_ROW,
    FINDING_OPS_READINESS_ROW,
    FINDING_RESOLVED_ROW,
    FINDING_SECURITY_ROW,
    FINDING_SUPPRESSED_ROW,
    FINDING_TEST_COVERAGE_ROW,
)

_NOW = datetime.now(timezone.utc)
_FUTURE_30D = _NOW + timedelta(days=30)
_ACTOR_ID = str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Routing logic
# ---------------------------------------------------------------------------

class TestRouteApprover:
    def test_security_routes_to_security_reviewer(self):
        assert _route_approver("security") == "security_reviewer"

    def test_code_quality_routes_to_platform_admin(self):
        assert _route_approver("code_quality") == "platform_admin"

    def test_test_coverage_routes_to_platform_admin(self):
        assert _route_approver("test_coverage") == "platform_admin"

    def test_documentation_routes_to_platform_admin(self):
        assert _route_approver("documentation") == "platform_admin"

    def test_operations_readiness_routes_to_platform_admin(self):
        assert _route_approver("operations_readiness") == "platform_admin"

    def test_unknown_dimension_routes_to_platform_admin(self):
        assert _route_approver("unknown_dimension") == "platform_admin"

    def test_empty_dimension_routes_to_platform_admin(self):
        assert _route_approver("") == "platform_admin"


# ---------------------------------------------------------------------------
# Pydantic validation — ExceptionRequest
# ---------------------------------------------------------------------------

class TestExceptionRequestValidation:
    def test_valid_request(self):
        req = ExceptionRequest(
            justification="This cannot be patched until Q3 due to vendor freeze.",
            expires_at=_FUTURE_30D,
        )
        assert req.justification.startswith("This cannot")

    def test_justification_exactly_20_chars(self):
        req = ExceptionRequest(
            justification="A" * 20,
            expires_at=_FUTURE_30D,
        )
        assert len(req.justification) == 20

    def test_justification_19_chars_raises(self):
        with pytest.raises(Exception, match="20 characters"):
            ExceptionRequest(
                justification="A" * 19,
                expires_at=_FUTURE_30D,
            )

    def test_justification_whitespace_trimmed_then_validated(self):
        with pytest.raises(Exception, match="20 characters"):
            ExceptionRequest(
                justification="  short  ",
                expires_at=_FUTURE_30D,
            )

    def test_justification_leading_whitespace_trimmed(self):
        raw = "  " + "A" * 20
        req = ExceptionRequest(justification=raw, expires_at=_FUTURE_30D)
        assert req.justification == "A" * 20

    def test_expires_at_past_raises(self):
        with pytest.raises(Exception, match="future"):
            ExceptionRequest(
                justification="A" * 20,
                expires_at=_NOW - timedelta(seconds=1),
            )

    def test_expires_at_exactly_now_raises(self):
        with pytest.raises(Exception, match="future"):
            ExceptionRequest(
                justification="A" * 20,
                expires_at=_NOW,
            )

    def test_expires_at_91_days_raises(self):
        with pytest.raises(Exception, match="90 days"):
            ExceptionRequest(
                justification="A" * 20,
                expires_at=_NOW + timedelta(days=91),
            )

    def test_expires_at_exactly_90_days_valid(self):
        # 90 days minus a second is valid
        req = ExceptionRequest(
            justification="A" * 20,
            expires_at=_NOW + timedelta(days=89, hours=23, minutes=59),
        )
        assert req.expires_at > _NOW

    def test_expires_at_naive_datetime_accepted(self):
        naive = (_NOW + timedelta(days=5)).replace(tzinfo=None)
        req = ExceptionRequest(justification="A" * 20, expires_at=naive)
        assert req.expires_at is not None


# ---------------------------------------------------------------------------
# ExceptionService.submit_request
# ---------------------------------------------------------------------------

def _make_svc(
    finding_row=None,
    existing_pending=None,
    existing_active=None,
    created_row=None,
):
    finding_repo = MagicMock()
    finding_repo.get_by_id = AsyncMock(return_value=finding_row)

    exception_repo = MagicMock()
    exception_repo.check_existing_pending = AsyncMock(return_value=existing_pending)
    exception_repo.check_existing_approved_active = AsyncMock(
        return_value=existing_active
    )
    exception_repo.create = AsyncMock(return_value=created_row or dict(EXCEPTION_ROW))

    return ExceptionService(
        exception_repo=exception_repo,
        finding_repo=finding_repo,
        audit_service=None,
    )


class TestSubmitRequest:
    @pytest.mark.asyncio
    async def test_security_finding_routes_to_security_reviewer(self):
        svc = _make_svc(finding_row=dict(FINDING_SECURITY_ROW))
        result = await svc.submit_request(
            finding_id=FINDING_SECURITY_ROW["id"],
            justification="A" * 30,
            expires_at=_FUTURE_30D,
            actor_id=_ACTOR_ID,
            actor_role="developer",
        )
        # verify create was called with approver_role='security_reviewer'
        call_data = svc._exception_repo.create.call_args[0][0]
        assert call_data["approver_role"] == "security_reviewer"

    @pytest.mark.asyncio
    async def test_code_quality_finding_routes_to_platform_admin(self):
        svc = _make_svc(finding_row=dict(FINDING_CODE_QUALITY_ROW))
        await svc.submit_request(
            finding_id=FINDING_CODE_QUALITY_ROW["id"],
            justification="A" * 30,
            expires_at=_FUTURE_30D,
            actor_id=_ACTOR_ID,
            actor_role="developer",
        )
        call_data = svc._exception_repo.create.call_args[0][0]
        assert call_data["approver_role"] == "platform_admin"

    @pytest.mark.asyncio
    async def test_test_coverage_routes_to_platform_admin(self):
        svc = _make_svc(finding_row=dict(FINDING_TEST_COVERAGE_ROW))
        await svc.submit_request(
            finding_id=FINDING_TEST_COVERAGE_ROW["id"],
            justification="A" * 30,
            expires_at=_FUTURE_30D,
            actor_id=_ACTOR_ID,
            actor_role="developer",
        )
        call_data = svc._exception_repo.create.call_args[0][0]
        assert call_data["approver_role"] == "platform_admin"

    @pytest.mark.asyncio
    async def test_documentation_routes_to_platform_admin(self):
        svc = _make_svc(finding_row=dict(FINDING_DOCUMENTATION_ROW))
        await svc.submit_request(
            finding_id=FINDING_DOCUMENTATION_ROW["id"],
            justification="A" * 30,
            expires_at=_FUTURE_30D,
            actor_id=_ACTOR_ID,
            actor_role="developer",
        )
        call_data = svc._exception_repo.create.call_args[0][0]
        assert call_data["approver_role"] == "platform_admin"

    @pytest.mark.asyncio
    async def test_operations_readiness_routes_to_platform_admin(self):
        svc = _make_svc(finding_row=dict(FINDING_OPS_READINESS_ROW))
        await svc.submit_request(
            finding_id=FINDING_OPS_READINESS_ROW["id"],
            justification="A" * 30,
            expires_at=_FUTURE_30D,
            actor_id=_ACTOR_ID,
            actor_role="developer",
        )
        call_data = svc._exception_repo.create.call_args[0][0]
        assert call_data["approver_role"] == "platform_admin"

    @pytest.mark.asyncio
    async def test_status_is_pending(self):
        svc = _make_svc(finding_row=dict(FINDING_CODE_QUALITY_ROW))
        await svc.submit_request(
            finding_id=FINDING_CODE_QUALITY_ROW["id"],
            justification="A" * 30,
            expires_at=_FUTURE_30D,
            actor_id=_ACTOR_ID,
            actor_role="developer",
        )
        call_data = svc._exception_repo.create.call_args[0][0]
        assert call_data["status"] == "pending"

    @pytest.mark.asyncio
    async def test_actor_id_recorded(self):
        svc = _make_svc(finding_row=dict(FINDING_CODE_QUALITY_ROW))
        await svc.submit_request(
            finding_id=FINDING_CODE_QUALITY_ROW["id"],
            justification="A" * 30,
            expires_at=_FUTURE_30D,
            actor_id=_ACTOR_ID,
            actor_role="developer",
        )
        call_data = svc._exception_repo.create.call_args[0][0]
        assert str(call_data["requested_by"]) == _ACTOR_ID

    @pytest.mark.asyncio
    async def test_finding_not_found_raises_not_found(self):
        svc = _make_svc(finding_row=None)
        with pytest.raises(NotFoundError):
            await svc.submit_request(
                finding_id=uuid.uuid4(),
                justification="A" * 30,
                expires_at=_FUTURE_30D,
                actor_id=_ACTOR_ID,
                actor_role="developer",
            )

    @pytest.mark.asyncio
    async def test_resolved_finding_raises_bad_request(self):
        svc = _make_svc(finding_row=dict(FINDING_RESOLVED_ROW))
        with pytest.raises(BadRequestError, match="resolved"):
            await svc.submit_request(
                finding_id=FINDING_RESOLVED_ROW["id"],
                justification="A" * 30,
                expires_at=_FUTURE_30D,
                actor_id=_ACTOR_ID,
                actor_role="developer",
            )

    @pytest.mark.asyncio
    async def test_suppressed_finding_raises_bad_request(self):
        svc = _make_svc(finding_row=dict(FINDING_SUPPRESSED_ROW))
        with pytest.raises(BadRequestError, match="suppressed"):
            await svc.submit_request(
                finding_id=FINDING_SUPPRESSED_ROW["id"],
                justification="A" * 30,
                expires_at=_FUTURE_30D,
                actor_id=_ACTOR_ID,
                actor_role="developer",
            )

    @pytest.mark.asyncio
    async def test_duplicate_pending_raises_conflict(self):
        svc = _make_svc(
            finding_row=dict(FINDING_CODE_QUALITY_ROW),
            existing_pending=dict(EXCEPTION_ROW),
        )
        with pytest.raises(ConflictError, match="already pending"):
            await svc.submit_request(
                finding_id=FINDING_CODE_QUALITY_ROW["id"],
                justification="A" * 30,
                expires_at=_FUTURE_30D,
                actor_id=_ACTOR_ID,
                actor_role="developer",
            )

    @pytest.mark.asyncio
    async def test_active_approved_raises_conflict(self):
        svc = _make_svc(
            finding_row=dict(FINDING_CODE_QUALITY_ROW),
            existing_active=dict(EXCEPTION_ROW),
        )
        with pytest.raises(ConflictError, match="active approved"):
            await svc.submit_request(
                finding_id=FINDING_CODE_QUALITY_ROW["id"],
                justification="A" * 30,
                expires_at=_FUTURE_30D,
                actor_id=_ACTOR_ID,
                actor_role="developer",
            )

    @pytest.mark.asyncio
    async def test_audit_logged_on_success(self):
        audit = MagicMock()
        audit.log_event = AsyncMock()
        finding_repo = MagicMock()
        finding_repo.get_by_id = AsyncMock(return_value=dict(FINDING_CODE_QUALITY_ROW))
        exception_repo = MagicMock()
        exception_repo.check_existing_pending = AsyncMock(return_value=None)
        exception_repo.check_existing_approved_active = AsyncMock(return_value=None)
        exception_repo.create = AsyncMock(return_value=dict(EXCEPTION_ROW))

        svc = ExceptionService(
            exception_repo=exception_repo,
            finding_repo=finding_repo,
            audit_service=audit,
        )
        await svc.submit_request(
            finding_id=FINDING_CODE_QUALITY_ROW["id"],
            justification="A" * 30,
            expires_at=_FUTURE_30D,
            actor_id=_ACTOR_ID,
            actor_role="developer",
        )
        audit.log_event.assert_called_once()
        kwargs = audit.log_event.call_args.kwargs
        assert kwargs["action"] == "exception.requested"
        assert kwargs["resource_type"] == "exception"
