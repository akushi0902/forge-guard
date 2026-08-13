"""Pydantic schemas for the Compliance Report Export API (WO-093)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, field_validator, model_validator

from forgeguard.core.validation import ForgeGuardBaseModel


# ---------------------------------------------------------------------------
# Query parameters
# ---------------------------------------------------------------------------


class ComplianceReportQuery(BaseModel):
    """Validated query parameters for GET /api/v1/reports/compliance."""

    start_date: date
    end_date: date
    format: str = "json"
    service_id: Optional[uuid.UUID] = None

    @field_validator("format")
    @classmethod
    def validate_format(cls, v: str) -> str:
        if v not in ("json", "csv"):
            raise ValueError("format must be json or csv")
        return v

    @model_validator(mode="after")
    def validate_date_range(self) -> "ComplianceReportQuery":
        if self.end_date < self.start_date:
            raise ValueError("end_date must be greater than or equal to start_date")
        delta = (self.end_date - self.start_date).days
        if delta > 365:
            raise ValueError("Date range must not exceed 365 days")
        return self


# ---------------------------------------------------------------------------
# Health score trend models
# ---------------------------------------------------------------------------


class WeeklyScorePoint(ForgeGuardBaseModel):
    week_start: date
    avg_score: Optional[Decimal] = None
    dimension_scores: dict[str, Optional[Decimal]] = {}


class ServiceHealthTrend(ForgeGuardBaseModel):
    service_id: uuid.UUID
    service_name: str
    weekly_scores: list[WeeklyScorePoint] = []


# ---------------------------------------------------------------------------
# Findings summary
# ---------------------------------------------------------------------------


class FindingsBySeverity(ForgeGuardBaseModel):
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0


class FindingsByStatus(ForgeGuardBaseModel):
    open: int = 0
    resolved: int = 0
    excepted: int = 0


class FindingsSummary(ForgeGuardBaseModel):
    total: int = 0
    by_severity: FindingsBySeverity = FindingsBySeverity()
    by_status: FindingsByStatus = FindingsByStatus()


# ---------------------------------------------------------------------------
# Remediation metrics
# ---------------------------------------------------------------------------


class RemediationMetrics(ForgeGuardBaseModel):
    mean_time_to_remediation_hours: Optional[Decimal] = None
    findings_resolved: int = 0
    findings_open: int = 0


# ---------------------------------------------------------------------------
# Exceptions summary
# ---------------------------------------------------------------------------


class ExceptionsByStatus(ForgeGuardBaseModel):
    requested: int = 0
    approved: int = 0
    denied: int = 0
    expired: int = 0


class ExceptionsSummary(ForgeGuardBaseModel):
    total: int = 0
    by_status: ExceptionsByStatus = ExceptionsByStatus()


# ---------------------------------------------------------------------------
# Report period / actor
# ---------------------------------------------------------------------------


class ReportPeriod(ForgeGuardBaseModel):
    start_date: date
    end_date: date


class ReportActor(ForgeGuardBaseModel):
    user_id: uuid.UUID
    role: str


# ---------------------------------------------------------------------------
# Top-level response
# ---------------------------------------------------------------------------


class ComplianceReportResponse(ForgeGuardBaseModel):
    report_period: ReportPeriod
    generated_at: datetime
    generated_by: ReportActor
    services_included: int = 0
    health_score_trends: list[ServiceHealthTrend] = []
    findings_summary: FindingsSummary = FindingsSummary()
    remediation_metrics: RemediationMetrics = RemediationMetrics()
    exceptions_summary: ExceptionsSummary = ExceptionsSummary()
