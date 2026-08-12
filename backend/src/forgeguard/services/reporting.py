"""ComplianceReportService: report assembly and CSV generation (WO-093).

Orchestrates four ReportingRepository aggregation queries, assembles the
ComplianceReportResponse, and provides RFC 4180-compliant CSV generation
via the Python csv module.
"""

from __future__ import annotations

import csv
import io
import uuid
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Generator, Optional

import structlog

from forgeguard.api.schemas.reports import (
    ComplianceReportResponse,
    ExceptionsByStatus,
    ExceptionsSummary,
    FindingsBySeverity,
    FindingsByStatus,
    FindingsSummary,
    RemediationMetrics,
    ReportActor,
    ReportPeriod,
    ServiceHealthTrend,
    WeeklyScorePoint,
)
from forgeguard.data.repositories.reporting_repository import ReportingRepository

logger = structlog.get_logger(__name__)

_SECONDS_PER_HOUR = 3600.0

# CSV columns per the API contract
_CSV_HEADERS = [
    "service_id",
    "service_name",
    "week_start",
    "avg_health_score",
    "code_quality_score",
    "test_coverage_score",
    "security_score",
    "documentation_score",
    "operations_readiness_score",
    "critical_findings",
    "high_findings",
    "medium_findings",
    "low_findings",
    "open_findings",
    "resolved_findings",
    "excepted_findings",
    "mttr_hours",
    "exceptions_requested",
    "exceptions_approved",
    "exceptions_denied",
    "exceptions_expired",
]


class ComplianceReportService:
    """Assembles compliance reports from aggregated repository data."""

    def __init__(self, repo: ReportingRepository) -> None:
        self._repo = repo

    async def generate_report(
        self,
        *,
        start_date: date,
        end_date: date,
        service_id: Optional[uuid.UUID],
        actor_id: uuid.UUID,
        actor_role: str,
    ) -> ComplianceReportResponse:
        """Run all four aggregation queries and assemble the report."""
        log = logger.bind(start_date=str(start_date), end_date=str(end_date))
        log.info("compliance_report_generating")

        # Run all four aggregation queries
        trend_rows = await self._repo.get_health_score_trends_simple(
            start_date, end_date, service_id
        )
        finding_rows = await self._repo.get_findings_summary(
            start_date, end_date, service_id
        )
        remediation_row = await self._repo.get_remediation_metrics(
            start_date, end_date, service_id
        )
        exception_rows = await self._repo.get_exceptions_summary(
            start_date, end_date, service_id
        )

        health_trends = self._build_health_trends(trend_rows)
        findings_summary = self._build_findings_summary(finding_rows)
        remediation_metrics = self._build_remediation_metrics(remediation_row)
        exceptions_summary = self._build_exceptions_summary(exception_rows)

        services_included = len(health_trends)

        return ComplianceReportResponse(
            report_period=ReportPeriod(start_date=start_date, end_date=end_date),
            generated_at=datetime.now(timezone.utc),
            generated_by=ReportActor(user_id=actor_id, role=actor_role),
            services_included=services_included,
            health_score_trends=health_trends,
            findings_summary=findings_summary,
            remediation_metrics=remediation_metrics,
            exceptions_summary=exceptions_summary,
        )

    # ------------------------------------------------------------------
    # Builders
    # ------------------------------------------------------------------

    def _build_health_trends(
        self, rows: list[dict[str, Any]]
    ) -> list[ServiceHealthTrend]:
        services: dict[str, ServiceHealthTrend] = {}
        for row in rows:
            sid = str(row["service_id"])
            if sid not in services:
                services[sid] = ServiceHealthTrend(
                    service_id=row["service_id"],
                    service_name=row["service_name"],
                    weekly_scores=[],
                )
            dim_raw = row.get("dimension_scores") or {}
            dim_scores: dict[str, Optional[Decimal]] = {
                k: Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                if v is not None else None
                for k, v in dim_raw.items()
            }
            avg = row.get("avg_score")
            week_point = WeeklyScorePoint(
                week_start=row["week_start"],
                avg_score=(
                    Decimal(str(avg)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                    if avg is not None else None
                ),
                dimension_scores=dim_scores,
            )
            services[sid].weekly_scores.append(week_point)
        return list(services.values())

    def _build_findings_summary(
        self, rows: list[dict[str, Any]]
    ) -> FindingsSummary:
        by_sev: dict[str, int] = defaultdict(int)
        by_status: dict[str, int] = defaultdict(int)
        for row in rows:
            count = int(row["count"])
            by_sev[row["severity"]] += count
            status = row["status"]
            # Map 'suppressed' (active exception) to 'excepted'
            if status == "suppressed":
                by_status["excepted"] += count
            elif status in ("open", "in_progress"):
                by_status["open"] += count
            elif status == "resolved":
                by_status["resolved"] += count
        total = sum(by_sev.values())
        return FindingsSummary(
            total=total,
            by_severity=FindingsBySeverity(
                critical=by_sev.get("critical", 0),
                high=by_sev.get("high", 0),
                medium=by_sev.get("medium", 0),
                low=by_sev.get("low", 0),
            ),
            by_status=FindingsByStatus(
                open=by_status.get("open", 0),
                resolved=by_status.get("resolved", 0),
                excepted=by_status.get("excepted", 0),
            ),
        )

    def _build_remediation_metrics(
        self, row: dict[str, Any]
    ) -> RemediationMetrics:
        mean_ttr_sec = row.get("mean_ttr_seconds")
        mean_ttr_hours: Optional[Decimal] = None
        if mean_ttr_sec is not None:
            mean_ttr_hours = Decimal(str(float(mean_ttr_sec) / _SECONDS_PER_HOUR)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        return RemediationMetrics(
            mean_time_to_remediation_hours=mean_ttr_hours,
            findings_resolved=int(row.get("findings_resolved") or 0),
            findings_open=int(row.get("findings_open") or 0),
        )

    def _build_exceptions_summary(
        self, rows: list[dict[str, Any]]
    ) -> ExceptionsSummary:
        by_status: dict[str, int] = defaultdict(int)
        for row in rows:
            by_status[row["status"]] = int(row["count"])
        total = sum(by_status.values())
        return ExceptionsSummary(
            total=total,
            by_status=ExceptionsByStatus(
                requested=by_status.get("requested", 0),
                approved=by_status.get("approved", 0),
                denied=by_status.get("denied", 0),
                expired=by_status.get("expired", 0),
            ),
        )

    # ------------------------------------------------------------------
    # CSV generation (RFC 4180, generator-based for streaming)
    # ------------------------------------------------------------------

    def generate_csv(
        self, report: ComplianceReportResponse
    ) -> Generator[str, None, None]:
        """Yield CSV rows as strings for streaming.

        Uses the Python csv module for RFC 4180 compliance.
        Each yield is one or more complete rows.
        """
        buf = io.StringIO()
        writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")

        # Header row
        writer.writerow(_CSV_HEADERS)
        yield buf.getvalue()
        buf.truncate(0)
        buf.seek(0)

        # Pre-aggregate findings and exceptions for flat rows
        fs = report.findings_summary
        es = report.exceptions_summary
        rm = report.remediation_metrics

        for trend in report.health_score_trends:
            if not trend.weekly_scores:
                # Service with no score data — emit one placeholder row
                writer.writerow(self._flat_row(
                    service_id=str(trend.service_id),
                    service_name=trend.service_name,
                    week_start="",
                    avg_score="",
                    dims={},
                    fs=fs,
                    rm=rm,
                    es=es,
                ))
                yield buf.getvalue()
                buf.truncate(0)
                buf.seek(0)
            else:
                for wp in trend.weekly_scores:
                    writer.writerow(self._flat_row(
                        service_id=str(trend.service_id),
                        service_name=trend.service_name,
                        week_start=str(wp.week_start),
                        avg_score=str(wp.avg_score) if wp.avg_score is not None else "",
                        dims=wp.dimension_scores,
                        fs=fs,
                        rm=rm,
                        es=es,
                    ))
                    yield buf.getvalue()
                    buf.truncate(0)
                    buf.seek(0)

    @staticmethod
    def _flat_row(
        *,
        service_id: str,
        service_name: str,
        week_start: str,
        avg_score: str,
        dims: dict[str, Any],
        fs: FindingsSummary,
        rm: RemediationMetrics,
        es: ExceptionsSummary,
    ) -> list[Any]:
        return [
            service_id,
            service_name,
            week_start,
            avg_score,
            dims.get("code_quality", ""),
            dims.get("test_coverage", ""),
            dims.get("security", ""),
            dims.get("documentation", ""),
            dims.get("operations_readiness", ""),
            fs.by_severity.critical,
            fs.by_severity.high,
            fs.by_severity.medium,
            fs.by_severity.low,
            fs.by_status.open,
            fs.by_status.resolved,
            fs.by_status.excepted,
            str(rm.mean_time_to_remediation_hours) if rm.mean_time_to_remediation_hours is not None else "",
            es.by_status.requested,
            es.by_status.approved,
            es.by_status.denied,
            es.by_status.expired,
        ]

    def generate_csv_string(self, report: ComplianceReportResponse) -> str:
        """Generate the full CSV as a string (for non-streaming responses)."""
        return "".join(self.generate_csv(report))
