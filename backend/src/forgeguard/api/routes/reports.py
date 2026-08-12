"""Compliance Report Export API (WO-093).

Routes:
    GET /api/v1/reports/compliance — generate and return a compliance report

RBAC: Restricted to engineering_manager and platform_admin roles.
Streaming: date ranges > 90 days use StreamingResponse.
Audit: every export request is logged with actor, date range, format, row count.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Annotated, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse

from forgeguard.api.dependencies.audit import get_audit_service
from forgeguard.api.dependencies.auth import CurrentUserDep
from forgeguard.api.schemas.reports import ComplianceReportQuery, ComplianceReportResponse
from forgeguard.core.dependencies import get_pool
from forgeguard.core.permissions import UserRole
from forgeguard.data.repositories.reporting_repository import ReportingRepository
from forgeguard.services.audit import AuditService
from forgeguard.services.reporting import ComplianceReportService

import asyncpg

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])

_ALLOWED_ROLES = frozenset({UserRole.engineering_manager, UserRole.platform_admin})
_STREAMING_THRESHOLD_DAYS = 90

_RBAC_ERROR = (
    "This action requires the engineering_manager or platform_admin role. "
    "Contact your Platform Admin for access."
)


# ---------------------------------------------------------------------------
# Dependency: reporting service
# ---------------------------------------------------------------------------


async def get_reporting_service(
    pool: asyncpg.Pool = Depends(get_pool),
) -> ComplianceReportService:
    return ComplianceReportService(ReportingRepository(pool))


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.get(
    "/compliance",
    summary="Export compliance report (JSON or CSV)",
    description=(
        "Generates an aggregated compliance report for the given date range. "
        "Restricted to Engineering Manager and Platform Admin roles. "
        "Date ranges > 90 days use streaming to avoid memory exhaustion."
    ),
    response_model=None,
)
async def get_compliance_report(
    current_user: CurrentUserDep,
    start_date: Annotated[date, Query(description="Report start date (YYYY-MM-DD)")],
    end_date: Annotated[date, Query(description="Report end date (YYYY-MM-DD)")],
    format: Annotated[str, Query(description="Response format: json or csv")] = "json",
    service_id: Annotated[Optional[uuid.UUID], Query(description="Filter by service UUID")] = None,
    report_svc: ComplianceReportService = Depends(get_reporting_service),
    audit: AuditService = Depends(get_audit_service),
    pool: asyncpg.Pool = Depends(get_pool),
):
    # RBAC check
    if current_user.role not in _ALLOWED_ROLES:
        raise HTTPException(status_code=403, detail=_RBAC_ERROR)

    # Validate parameters via Pydantic
    try:
        query = ComplianceReportQuery(
            start_date=start_date,
            end_date=end_date,
            format=format,
            service_id=service_id,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Validate service_id exists
    if service_id is not None:
        repo = ReportingRepository(pool)
        exists = await repo.service_exists(service_id)
        if not exists:
            raise HTTPException(status_code=404, detail=f"Service {service_id} not found")

    log = logger.bind(
        actor_id=str(current_user.user_id),
        actor_role=current_user.role,
        start_date=str(query.start_date),
        end_date=str(query.end_date),
        format=query.format,
        service_id=str(service_id) if service_id else None,
    )
    log.info("report_export_requested")

    # Audit: export started
    await audit.log_event(
        actor_id=current_user.user_id,
        actor_role=current_user.role,
        action="report_export_requested",
        resource_type="compliance_report",
        metadata={
            "start_date": str(query.start_date),
            "end_date": str(query.end_date),
            "format": query.format,
            "service_id": str(service_id) if service_id else None,
        },
    )

    report = await report_svc.generate_report(
        start_date=query.start_date,
        end_date=query.end_date,
        service_id=service_id,
        actor_id=current_user.user_id,
        actor_role=current_user.role,
    )

    date_range_days = (query.end_date - query.start_date).days
    row_count = report.services_included

    # Audit: export completed
    await audit.log_event(
        actor_id=current_user.user_id,
        actor_role=current_user.role,
        action="report_export_completed",
        resource_type="compliance_report",
        after_state={
            "services_included": row_count,
            "format": query.format,
        },
        metadata={
            "start_date": str(query.start_date),
            "end_date": str(query.end_date),
            "format": query.format,
            "service_id": str(service_id) if service_id else None,
            "row_count": row_count,
        },
    )

    log.info("report_export_completed", row_count=row_count)

    if query.format == "csv":
        filename = (
            f"compliance-report-{query.start_date}-{query.end_date}.csv"
        )
        if date_range_days > _STREAMING_THRESHOLD_DAYS:
            # Streaming response for large ranges
            return StreamingResponse(
                report_svc.generate_csv(report),
                media_type="text/csv",
                headers={
                    "Content-Disposition": f"attachment; filename={filename}",
                },
            )
        # Small range — return full CSV
        csv_body = report_svc.generate_csv_string(report)
        return StreamingResponse(
            iter([csv_body]),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
            },
        )

    # JSON response
    return JSONResponse(
        content=report.model_dump(mode="json"),
    )
