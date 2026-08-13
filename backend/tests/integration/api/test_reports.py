"""Integration tests for GET /api/v1/reports/compliance (WO-093).

Validates:
  - JSON and CSV format responses with mocked data
  - RBAC: EM and PA receive 200; developer/tech_lead/security_reviewer/operator receive 403
  - Date range validation (end < start → 400, > 365 days → 400)
  - Service filter: nonexistent service → 404
  - Streaming response for date ranges > 90 days
  - Audit log records produced for every successful export
  - Empty report returns zero counts, not 404

All database calls are mocked — no running PostgreSQL required.

Run:
    pytest tests/integration/api/test_reports.py -v
"""

from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from forgeguard.services.reporting import ComplianceReportService
from tests.fixtures.reporting_data import (
    EXCEPTIONS_SUMMARY_ROWS,
    EXCEPTIONS_SUMMARY_ROWS_EMPTY,
    FINDINGS_SUMMARY_ROWS,
    FINDINGS_SUMMARY_ROWS_EMPTY,
    HEALTH_TREND_ROWS,
    HEALTH_TREND_ROWS_EMPTY,
    REMEDIATION_ROW,
    REMEDIATION_ROW_EMPTY,
    REPORT_END_DATE,
    REPORT_END_LONG,
    REPORT_START_DATE,
    REPORT_START_LONG,
    SERVICE_A_ID,
)

_ACTOR_ID = uuid.UUID("20000000-0000-0000-0000-000000000001")
_UNKNOWN_SERVICE_ID = uuid.UUID("99999999-9999-9999-9999-999999999999")


def _mock_user(role: str = "engineering_manager"):
    from forgeguard.api.dependencies.auth import CurrentUser
    return CurrentUser(user_id=_ACTOR_ID, role=role)


def _make_report_svc(
    *,
    trends=None,
    findings=None,
    remediation=None,
    exceptions=None,
) -> ComplianceReportService:
    from forgeguard.data.repositories.reporting_repository import ReportingRepository
    repo = MagicMock(spec=ReportingRepository)
    repo.get_health_score_trends_simple = AsyncMock(
        return_value=trends if trends is not None else HEALTH_TREND_ROWS
    )
    repo.get_findings_summary = AsyncMock(
        return_value=findings if findings is not None else FINDINGS_SUMMARY_ROWS
    )
    repo.get_remediation_metrics = AsyncMock(
        return_value=remediation if remediation is not None else REMEDIATION_ROW
    )
    repo.get_exceptions_summary = AsyncMock(
        return_value=exceptions if exceptions is not None else EXCEPTIONS_SUMMARY_ROWS
    )
    return ComplianceReportService(repo)


def _make_repo(service_exists: bool = True):
    from forgeguard.data.repositories.reporting_repository import ReportingRepository
    repo = MagicMock(spec=ReportingRepository)
    repo.service_exists = AsyncMock(return_value=service_exists)
    return repo


async def _call_endpoint(
    *,
    start_date: date = REPORT_START_DATE,
    end_date: date = REPORT_END_DATE,
    format: str = "json",
    service_id=None,
    role: str = "engineering_manager",
    report_svc=None,
    service_exists: bool = True,
):
    from forgeguard.api.routes.reports import get_compliance_report
    from forgeguard.data.repositories.reporting_repository import ReportingRepository

    current_user = _mock_user(role)
    audit = MagicMock()
    audit.log_event = AsyncMock(return_value=None)
    pool = MagicMock()

    if report_svc is None:
        report_svc = _make_report_svc()

    # Patch ReportingRepository for service_exists check
    from unittest.mock import patch
    repo_mock = _make_repo(service_exists)

    with patch(
        "forgeguard.api.routes.reports.ReportingRepository",
        return_value=repo_mock,
    ):
        return await get_compliance_report(
            current_user=current_user,
            start_date=start_date,
            end_date=end_date,
            format=format,
            service_id=service_id,
            report_svc=report_svc,
            audit=audit,
            pool=pool,
        )


# ---------------------------------------------------------------------------
# Happy path — JSON
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_json_report_returns_200_for_em():
    from fastapi.responses import JSONResponse
    resp = await _call_endpoint()
    assert isinstance(resp, JSONResponse)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_json_report_body_structure():
    from fastapi.responses import JSONResponse
    import json
    resp = await _call_endpoint()
    body = json.loads(resp.body)
    assert "report_period" in body
    assert "health_score_trends" in body
    assert "findings_summary" in body
    assert "remediation_metrics" in body
    assert "exceptions_summary" in body
    assert "generated_by" in body


@pytest.mark.asyncio
async def test_json_report_services_included():
    from fastapi.responses import JSONResponse
    import json
    resp = await _call_endpoint()
    body = json.loads(resp.body)
    assert body["services_included"] == 2


# ---------------------------------------------------------------------------
# Happy path — CSV
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_csv_report_returns_streaming_response():
    from fastapi.responses import StreamingResponse
    resp = await _call_endpoint(format="csv")
    assert isinstance(resp, StreamingResponse)
    assert resp.media_type == "text/csv"


@pytest.mark.asyncio
async def test_csv_report_content_disposition_header():
    resp = await _call_endpoint(format="csv")
    cd = resp.headers.get("content-disposition", "")
    assert "attachment" in cd
    assert "compliance-report" in cd
    assert str(REPORT_START_DATE) in cd


# ---------------------------------------------------------------------------
# Streaming for > 90 day ranges
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_streaming_response_for_long_range():
    from fastapi.responses import StreamingResponse
    resp = await _call_endpoint(
        start_date=REPORT_START_LONG,
        end_date=REPORT_END_LONG,
        format="csv",
    )
    assert isinstance(resp, StreamingResponse)


# ---------------------------------------------------------------------------
# RBAC enforcement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("role", [
    "developer", "tech_lead", "security_reviewer", "operator"
])
async def test_403_for_non_em_roles(role: str):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        await _call_endpoint(role=role)
    assert exc_info.value.status_code == 403
    assert "engineering_manager" in exc_info.value.detail


@pytest.mark.asyncio
async def test_200_for_platform_admin():
    from fastapi.responses import JSONResponse
    resp = await _call_endpoint(role="platform_admin")
    assert isinstance(resp, JSONResponse)
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Date validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_400_when_end_before_start():
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        await _call_endpoint(
            start_date=date(2026, 3, 31),
            end_date=date(2026, 1, 1),
        )
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_400_when_range_exceeds_365_days():
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        await _call_endpoint(
            start_date=date(2025, 1, 1),
            end_date=date(2026, 6, 1),  # > 365 days
        )
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_400_for_invalid_format():
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        await _call_endpoint(format="xml")
    assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# Service filter — not found
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_404_for_nonexistent_service():
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        await _call_endpoint(
            service_id=_UNKNOWN_SERVICE_ID,
            service_exists=False,
        )
    assert exc_info.value.status_code == 404
    assert str(_UNKNOWN_SERVICE_ID) in exc_info.value.detail


# ---------------------------------------------------------------------------
# Empty data — returns zero counts, not 404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_report_returns_200_with_zero_counts():
    from fastapi.responses import JSONResponse
    import json
    svc = _make_report_svc(
        trends=HEALTH_TREND_ROWS_EMPTY,
        findings=FINDINGS_SUMMARY_ROWS_EMPTY,
        remediation=REMEDIATION_ROW_EMPTY,
        exceptions=EXCEPTIONS_SUMMARY_ROWS_EMPTY,
    )
    resp = await _call_endpoint(report_svc=svc)
    assert isinstance(resp, JSONResponse)
    body = json.loads(resp.body)
    assert body["services_included"] == 0
    assert body["findings_summary"]["total"] == 0
    assert body["exceptions_summary"]["total"] == 0


# ---------------------------------------------------------------------------
# Audit logging compliance
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_log_called_on_successful_export():
    from forgeguard.api.routes.reports import get_compliance_report
    from unittest.mock import patch

    current_user = _mock_user()
    audit = MagicMock()
    audit.log_event = AsyncMock(return_value=None)
    pool = MagicMock()
    repo_mock = _make_repo(service_exists=True)
    report_svc = _make_report_svc()

    with patch("forgeguard.api.routes.reports.ReportingRepository", return_value=repo_mock):
        await get_compliance_report(
            current_user=current_user,
            start_date=REPORT_START_DATE,
            end_date=REPORT_END_DATE,
            format="json",
            service_id=None,
            report_svc=report_svc,
            audit=audit,
            pool=pool,
        )

    assert audit.log_event.call_count == 2
    actions = [c.kwargs["action"] for c in audit.log_event.call_args_list]
    assert "report_export_requested" in actions
    assert "report_export_completed" in actions
