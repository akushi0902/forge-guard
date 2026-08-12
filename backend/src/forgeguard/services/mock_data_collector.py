"""MockDataCollector: hardcoded normalized data for the Payment Service demo (WO-042).

Returns deterministic data that produces a mix of passing and failing rules across
all five governance dimensions.  Used for MVP and integration testing; replace with
a real data source adapter in production.

Data key naming convention matches the ``data_key`` fields in seed policy rules:
    - code_quality:         cyclomatic_complexity_avg, code_duplication_pct, tech_debt_ratio
    - test_coverage:        unit_test_coverage, integration_test_coverage, mutation_score
    - security:             dependency_vulnerabilities, critical_cve_count, secrets_detected
    - documentation:        has_readme, api_docs_complete, changelog_updated
    - operations_readiness: has_runbook, slo_defined, on_call_rotation_defined, deployment_automated
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog

from forgeguard.services.interfaces.data_collector import DataCollector

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Payment Service demo fixture data
# ---------------------------------------------------------------------------

_PAYMENT_SERVICE_DATA: dict[str, Any] = {
    # ── code_quality ─────────────────────────────────────────────────────────
    "cyclomatic_complexity_avg": 8.2,        # threshold ≤10 → PASS
    "code_duplication_pct": 15.0,            # threshold ≤20% → PASS
    "tech_debt_ratio": 0.12,                 # threshold ≤0.15 → PASS
    "lines_of_code": 12400,

    # ── test_coverage ────────────────────────────────────────────────────────
    "unit_test_coverage": 62.5,              # threshold ≥80% → FAIL
    "integration_test_coverage": 45.0,       # threshold ≥60% → FAIL
    "mutation_score": 38.0,                  # threshold ≥50% → FAIL

    # ── security ─────────────────────────────────────────────────────────────
    "dependency_vulnerabilities": 7,         # threshold ==0 → FAIL
    "critical_cve_count": 2,                 # threshold ==0 → FAIL
    "high_cve_count": 5,                     # threshold ≤2 → FAIL
    "secrets_detected": 0,                   # threshold ==0 → PASS
    "sast_findings_critical": 0,             # threshold ==0 → PASS

    # ── documentation ────────────────────────────────────────────────────────
    "has_readme": False,                     # threshold ==True → FAIL
    "api_docs_complete": False,              # threshold ==True → FAIL
    "changelog_updated": True,              # threshold ==True → PASS
    "architecture_doc_exists": False,        # threshold ==True → FAIL

    # ── operations_readiness ────────────────────────────────────────────────
    "has_runbook": True,                     # threshold ==True → PASS
    "slo_defined": False,                    # threshold ==True → FAIL
    "on_call_rotation_defined": True,        # threshold ==True → PASS
    "deployment_automated": True,            # threshold ==True → PASS
    "monitoring_configured": False,          # threshold ==True → FAIL
}

# Generic fallback for unknown services — intentionally shows healthier data
_DEFAULT_SERVICE_DATA: dict[str, Any] = {
    "cyclomatic_complexity_avg": 6.0,
    "code_duplication_pct": 8.0,
    "tech_debt_ratio": 0.05,
    "unit_test_coverage": 85.0,
    "integration_test_coverage": 70.0,
    "mutation_score": 55.0,
    "dependency_vulnerabilities": 0,
    "critical_cve_count": 0,
    "high_cve_count": 0,
    "secrets_detected": 0,
    "sast_findings_critical": 0,
    "has_readme": True,
    "api_docs_complete": True,
    "changelog_updated": True,
    "architecture_doc_exists": True,
    "has_runbook": True,
    "slo_defined": True,
    "on_call_rotation_defined": True,
    "deployment_automated": True,
    "monitoring_configured": True,
    "lines_of_code": 5000,
}


class MockDataCollector(DataCollector):
    """Returns hardcoded normalized data for the Payment Service demo.

    For the known Payment Service demo UUID, returns realistic data that
    triggers a mix of passing and failing rules.  Falls back to healthier
    default data for all other services.
    """

    # The Payment Service demo service UUID from seed data (WO-014)
    PAYMENT_SERVICE_ID = uuid.UUID("d0000000-0000-0000-0000-000000000001")

    async def collect(self, service_id: uuid.UUID) -> dict[str, Any]:
        if service_id == self.PAYMENT_SERVICE_ID:
            data = dict(_PAYMENT_SERVICE_DATA)
            logger.info(
                "mock_data_collector.payment_service_data",
                service_id=str(service_id),
                keys=len(data),
            )
        else:
            data = dict(_DEFAULT_SERVICE_DATA)
            logger.info(
                "mock_data_collector.default_data",
                service_id=str(service_id),
                keys=len(data),
            )
        return data
