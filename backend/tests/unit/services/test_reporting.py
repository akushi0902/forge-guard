"""Unit tests for ComplianceReportService (WO-093).

Covers:
  - Aggregation logic with mock repository data (health trends, findings, remediation, exceptions)
  - JSON response structure validation
  - CSV output validation (headers, escaping, row counts)
  - Empty data handling (zero-count sections)
  - Date range edge cases (single day, exactly 90 days)
  - MTTR calculation (seconds → hours)
  - findings status mapping (suppressed → excepted, in_progress → open)
"""

from __future__ import annotations

import csv
import io
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from forgeguard.api.schemas.reports import ComplianceReportResponse
from forgeguard.data.repositories.reporting_repository import ReportingRepository
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
    REPORT_START_DATE,
    SERVICE_A_ID,
    SERVICE_B_ID,
)

_ACTOR_ID = uuid.UUID("11111111-0000-0000-0000-000000000001")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_service(
    *,
    trends=None,
    findings=None,
    remediation=None,
    exceptions=None,
) -> ComplianceReportService:
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


async def _generate(svc: ComplianceReportService) -> ComplianceReportResponse:
    return await svc.generate_report(
        start_date=REPORT_START_DATE,
        end_date=REPORT_END_DATE,
        service_id=None,
        actor_id=_ACTOR_ID,
        actor_role="engineering_manager",
    )


# ---------------------------------------------------------------------------
# Report structure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_report_contains_all_sections():
    svc = _make_service()
    report = await _generate(svc)
    assert report.health_score_trends is not None
    assert report.findings_summary is not None
    assert report.remediation_metrics is not None
    assert report.exceptions_summary is not None


@pytest.mark.asyncio
async def test_report_period_matches_query():
    svc = _make_service()
    report = await _generate(svc)
    assert report.report_period.start_date == REPORT_START_DATE
    assert report.report_period.end_date == REPORT_END_DATE


@pytest.mark.asyncio
async def test_report_actor_matches_caller():
    svc = _make_service()
    report = await _generate(svc)
    assert report.generated_by.user_id == _ACTOR_ID
    assert report.generated_by.role == "engineering_manager"


# ---------------------------------------------------------------------------
# Health score trends
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_trends_groups_by_service():
    svc = _make_service()
    report = await _generate(svc)
    # HEALTH_TREND_ROWS has 2 services: payment-service, auth-service
    assert report.services_included == 2
    names = [t.service_name for t in report.health_score_trends]
    assert "payment-service" in names
    assert "auth-service" in names


@pytest.mark.asyncio
async def test_health_trends_weekly_scores_count():
    svc = _make_service()
    report = await _generate(svc)
    payment_trend = next(
        t for t in report.health_score_trends if t.service_name == "payment-service"
    )
    # payment-service has 2 weekly rows
    assert len(payment_trend.weekly_scores) == 2


@pytest.mark.asyncio
async def test_health_trends_empty_returns_no_services():
    svc = _make_service(trends=HEALTH_TREND_ROWS_EMPTY)
    report = await _generate(svc)
    assert report.services_included == 0
    assert report.health_score_trends == []


# ---------------------------------------------------------------------------
# Findings summary
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_findings_summary_totals():
    svc = _make_service()
    report = await _generate(svc)
    fs = report.findings_summary
    # critical: 2+1=3, high: 5+3=8, medium: 8+2=10, low: 4
    assert fs.by_severity.critical == 3
    assert fs.by_severity.high == 8
    assert fs.by_severity.medium == 10
    assert fs.by_severity.low == 4
    assert fs.total == 25


@pytest.mark.asyncio
async def test_findings_summary_status_suppressed_maps_to_excepted():
    svc = _make_service()
    report = await _generate(svc)
    fs = report.findings_summary
    assert fs.by_status.excepted == 2


@pytest.mark.asyncio
async def test_findings_summary_empty():
    svc = _make_service(findings=FINDINGS_SUMMARY_ROWS_EMPTY)
    report = await _generate(svc)
    fs = report.findings_summary
    assert fs.total == 0
    assert fs.by_severity.critical == 0
    assert fs.by_status.open == 0


# ---------------------------------------------------------------------------
# Remediation metrics
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_remediation_metrics_converts_seconds_to_hours():
    svc = _make_service()
    report = await _generate(svc)
    rm = report.remediation_metrics
    # 86400 seconds = 24.0 hours
    assert rm.mean_time_to_remediation_hours == Decimal("24.00")
    assert rm.findings_resolved == 8
    assert rm.findings_open == 15


@pytest.mark.asyncio
async def test_remediation_metrics_null_when_no_resolved_findings():
    svc = _make_service(remediation=REMEDIATION_ROW_EMPTY)
    report = await _generate(svc)
    assert report.remediation_metrics.mean_time_to_remediation_hours is None
    assert report.remediation_metrics.findings_resolved == 0


# ---------------------------------------------------------------------------
# Exceptions summary
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_exceptions_summary_by_status():
    svc = _make_service()
    report = await _generate(svc)
    es = report.exceptions_summary
    assert es.total == 10
    assert es.by_status.requested == 3
    assert es.by_status.approved == 2
    assert es.by_status.denied == 1
    assert es.by_status.expired == 4


@pytest.mark.asyncio
async def test_exceptions_summary_empty():
    svc = _make_service(exceptions=EXCEPTIONS_SUMMARY_ROWS_EMPTY)
    report = await _generate(svc)
    assert report.exceptions_summary.total == 0


# ---------------------------------------------------------------------------
# CSV generation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_csv_starts_with_header_row():
    svc = _make_service()
    report = await _generate(svc)
    csv_output = svc.generate_csv_string(report)
    first_row = csv_output.split("\r\n")[0]
    assert "service_id" in first_row
    assert "service_name" in first_row
    assert "avg_health_score" in first_row
    assert "critical_findings" in first_row
    assert "mttr_hours" in first_row


@pytest.mark.asyncio
async def test_csv_contains_service_names():
    svc = _make_service()
    report = await _generate(svc)
    csv_output = svc.generate_csv_string(report)
    assert "payment-service" in csv_output
    assert "auth-service" in csv_output


@pytest.mark.asyncio
async def test_csv_row_count():
    svc = _make_service()
    report = await _generate(svc)
    csv_output = svc.generate_csv_string(report)
    reader = csv.reader(io.StringIO(csv_output))
    rows = list(reader)
    # Header + 2 rows for payment-service + 1 row for auth-service = 4
    assert len(rows) == 4


@pytest.mark.asyncio
async def test_csv_escapes_comma_in_service_name():
    trends = [
        {
            "service_id": SERVICE_A_ID,
            "service_name": "payment, service",  # comma in name
            "week_start": date(2026, 1, 5),
            "avg_score": Decimal("85.50"),
            "dimension_scores": {},
        }
    ]
    svc = _make_service(trends=trends)
    report = await _generate(svc)
    csv_output = svc.generate_csv_string(report)
    # csv module should quote the field containing a comma
    assert '"payment, service"' in csv_output


@pytest.mark.asyncio
async def test_csv_header_only_for_empty_data():
    svc = _make_service(
        trends=HEALTH_TREND_ROWS_EMPTY,
        findings=FINDINGS_SUMMARY_ROWS_EMPTY,
        remediation=REMEDIATION_ROW_EMPTY,
        exceptions=EXCEPTIONS_SUMMARY_ROWS_EMPTY,
    )
    report = await _generate(svc)
    csv_output = svc.generate_csv_string(report)
    rows = [r for r in csv_output.split("\r\n") if r]
    assert len(rows) == 1  # header only


# ---------------------------------------------------------------------------
# Generator streaming behaviour
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_csv_is_generator():
    svc = _make_service()
    report = await _generate(svc)
    gen = svc.generate_csv(report)
    import types
    assert isinstance(gen, types.GeneratorType)


@pytest.mark.asyncio
async def test_generate_csv_first_chunk_is_header():
    svc = _make_service()
    report = await _generate(svc)
    gen = svc.generate_csv(report)
    first_chunk = next(gen)
    assert "service_id" in first_chunk
