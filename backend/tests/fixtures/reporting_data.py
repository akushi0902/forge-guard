"""Test fixture factories for compliance report data (WO-093).

Generates sample assessment_scores, findings, and exceptions spanning
configurable date ranges across multiple services.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

# ---------------------------------------------------------------------------
# Fixed IDs for reproducible tests
# ---------------------------------------------------------------------------

SERVICE_A_ID = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
SERVICE_B_ID = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000002")
SERVICE_C_ID = uuid.UUID("cccccccc-0000-0000-0000-000000000003")

ASSESSMENT_A_ID = uuid.UUID("aaaaaaaa-1111-0000-0000-000000000001")
ASSESSMENT_B_ID = uuid.UUID("bbbbbbbb-1111-0000-0000-000000000002")

# ---------------------------------------------------------------------------
# Health score trend rows (returned by ReportingRepository)
# ---------------------------------------------------------------------------

HEALTH_TREND_ROWS = [
    {
        "service_id": SERVICE_A_ID,
        "service_name": "payment-service",
        "week_start": date(2026, 1, 5),
        "avg_score": Decimal("85.50"),
        "dimension_scores": {
            "code_quality": 88.0,
            "test_coverage": 82.0,
            "security": 91.0,
            "documentation": 75.0,
            "operations_readiness": 84.0,
        },
    },
    {
        "service_id": SERVICE_A_ID,
        "service_name": "payment-service",
        "week_start": date(2026, 1, 12),
        "avg_score": Decimal("87.00"),
        "dimension_scores": {
            "code_quality": 90.0,
            "test_coverage": 84.0,
            "security": 93.0,
            "documentation": 78.0,
            "operations_readiness": 86.0,
        },
    },
    {
        "service_id": SERVICE_B_ID,
        "service_name": "auth-service",
        "week_start": date(2026, 1, 5),
        "avg_score": Decimal("72.00"),
        "dimension_scores": {
            "code_quality": 75.0,
            "test_coverage": 68.0,
            "security": 80.0,
            "documentation": 65.0,
            "operations_readiness": 70.0,
        },
    },
]

HEALTH_TREND_ROWS_EMPTY: list[dict[str, Any]] = []

# ---------------------------------------------------------------------------
# Findings summary rows (returned by ReportingRepository)
# ---------------------------------------------------------------------------

FINDINGS_SUMMARY_ROWS = [
    {"severity": "critical", "status": "open", "count": 2},
    {"severity": "critical", "status": "resolved", "count": 1},
    {"severity": "high", "status": "open", "count": 5},
    {"severity": "high", "status": "resolved", "count": 3},
    {"severity": "medium", "status": "open", "count": 8},
    {"severity": "medium", "status": "suppressed", "count": 2},
    {"severity": "low", "status": "resolved", "count": 4},
]

FINDINGS_SUMMARY_ROWS_EMPTY: list[dict[str, Any]] = []

# ---------------------------------------------------------------------------
# Remediation metrics rows
# ---------------------------------------------------------------------------

REMEDIATION_ROW = {
    "mean_ttr_seconds": 86400.0,  # 24 hours
    "findings_resolved": 8,
    "findings_open": 15,
}

REMEDIATION_ROW_EMPTY = {
    "mean_ttr_seconds": None,
    "findings_resolved": 0,
    "findings_open": 0,
}

# ---------------------------------------------------------------------------
# Exceptions summary rows
# ---------------------------------------------------------------------------

EXCEPTIONS_SUMMARY_ROWS = [
    {"status": "requested", "count": 3},
    {"status": "approved", "count": 2},
    {"status": "denied", "count": 1},
    {"status": "expired", "count": 4},
]

EXCEPTIONS_SUMMARY_ROWS_EMPTY: list[dict[str, Any]] = []

# ---------------------------------------------------------------------------
# Date range helpers
# ---------------------------------------------------------------------------

REPORT_START_DATE = date(2026, 1, 1)
REPORT_END_DATE = date(2026, 3, 31)  # 90 days
REPORT_START_LONG = date(2026, 1, 1)
REPORT_END_LONG = date(2026, 5, 1)   # > 90 days, triggers streaming


def make_date_range(days: int) -> tuple[date, date]:
    """Return (start, end) for a range of given days ending today."""
    end = date(2026, 8, 12)
    start = end - timedelta(days=days)
    return start, end
