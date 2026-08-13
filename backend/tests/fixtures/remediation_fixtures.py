"""Remediation recommendation test fixtures (WO-058).

Provides a MockLLMProvider, sample finding dicts covering all 5 dimensions
and 4 severity levels, and pre-built RecommendationResult objects for tests
that need deterministic outputs.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock

from forgeguard.services.ai_engine.models import LLMResponse, ResponseSource
from forgeguard.services.ai_engine.recommendation_generator import RecommendationResult

# ---------------------------------------------------------------------------
# Stable IDs
# ---------------------------------------------------------------------------

FINDING_CVE_ID = uuid.UUID("30000000-0000-0000-0000-000000000001")
FINDING_COVERAGE_ID = uuid.UUID("30000000-0000-0000-0000-000000000002")
FINDING_DOCS_ID = uuid.UUID("30000000-0000-0000-0000-000000000003")
FINDING_COMPLEXITY_ID = uuid.UUID("30000000-0000-0000-0000-000000000004")
FINDING_OPS_ID = uuid.UUID("30000000-0000-0000-0000-000000000005")

SERVICE_ID = uuid.UUID("40000000-0000-0000-0000-000000000001")
ASSESSMENT_ID = uuid.UUID("50000000-0000-0000-0000-000000000001")
REC_ID = uuid.UUID("60000000-0000-0000-0000-000000000001")


# ---------------------------------------------------------------------------
# Sample findings (all dimensions, all severity levels)
# ---------------------------------------------------------------------------

def _finding(
    *,
    id: uuid.UUID,
    severity: str,
    dimension: str,
    title: str,
    description: str = "",
    evidence: dict | None = None,
    status: str = "open",
) -> dict[str, Any]:
    return {
        "id": id,
        "assessment_id": ASSESSMENT_ID,
        "service_id": SERVICE_ID,
        "policy_rule_id": uuid.uuid4(),
        "severity": severity,
        "dimension": dimension,
        "status": status,
        "title": title,
        "description": description,
        "evidence": evidence or {},
        "escalation_required": severity == "critical" and dimension == "security",
    }


CRITICAL_SECURITY_FINDING = _finding(
    id=FINDING_CVE_ID,
    severity="critical",
    dimension="security",
    title="Critical CVE violation in security",
    description="Expected 0 but found 2 for Critical CVE Check",
    evidence={"actual_value": 2, "expected_value": 0, "data_key": "critical_cve_count"},
)

HIGH_COVERAGE_FINDING = _finding(
    id=FINDING_COVERAGE_ID,
    severity="high",
    dimension="test_coverage",
    title="Unit Test Coverage violation in test_coverage",
    description="Expected 80 but found 45 for Unit Test Coverage",
    evidence={"actual_value": 45.0, "expected_value": 80.0, "data_key": "unit_test_coverage"},
)

MEDIUM_DOCS_FINDING = _finding(
    id=FINDING_DOCS_ID,
    severity="medium",
    dimension="documentation",
    title="API Documentation violation in documentation",
    description="Expected True but found False for API Docs",
    evidence={"actual_value": False, "expected_value": True, "data_key": "api_docs_complete"},
)

LOW_COMPLEXITY_FINDING = _finding(
    id=FINDING_COMPLEXITY_ID,
    severity="low",
    dimension="code_quality",
    title="Complexity Check violation in code_quality",
    description="Expected 10 but found 15 for Cyclomatic Complexity",
    evidence={"actual_value": 15, "expected_value": 10, "data_key": "cyclomatic_complexity"},
)

HIGH_OPS_FINDING = _finding(
    id=FINDING_OPS_ID,
    severity="high",
    dimension="operations_readiness",
    title="Runbook Check violation in operations_readiness",
    description="Expected True but found False for Runbook Exists",
)

ALL_FINDINGS = [
    CRITICAL_SECURITY_FINDING,
    HIGH_COVERAGE_FINDING,
    MEDIUM_DOCS_FINDING,
    LOW_COMPLEXITY_FINDING,
    HIGH_OPS_FINDING,
]


# ---------------------------------------------------------------------------
# Pre-built recommendation results
# ---------------------------------------------------------------------------

AI_RECOMMENDATION_RESULT = RecommendationResult(
    recommendation_text="Update your dependency to resolve the critical CVE.",
    implementation_guide="1. Run `pip install --upgrade affected-package`\n2. Re-scan with the security tool.\n3. Deploy the fix.",
    business_impact="An unresolved critical CVE may block the release and expose the system to exploits.",
    confidence_score=0.85,
    source="ai_generated",
)

TEMPLATE_RECOMMENDATION_RESULT = RecommendationResult(
    recommendation_text="This critical finding in the security dimension requires attention.",
    implementation_guide="1. Review the evidence.\n2. Identify root cause.\n3. Fix and verify.\n4. Re-assess.",
    business_impact="A critical violation in security may impact release readiness.",
    confidence_score=0.50,
    source="template_fallback",
)


def make_persisted_recommendation(
    finding_id: uuid.UUID = FINDING_CVE_ID,
    result: RecommendationResult = AI_RECOMMENDATION_RESULT,
) -> dict[str, Any]:
    from datetime import datetime, timezone
    return {
        "id": REC_ID,
        "finding_id": finding_id,
        "recommendation_text": result.recommendation_text,
        "implementation_guide": result.implementation_guide,
        "business_impact": result.business_impact,
        "confidence_score": Decimal(str(round(result.confidence_score, 2))),
        "source": result.source,
        "created_at": datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
    }


# ---------------------------------------------------------------------------
# Mock LLM responses
# ---------------------------------------------------------------------------

LLM_RESPONSE_AI = LLMResponse(
    content=(
        "## Recommendation\n"
        "Update your dependency to resolve the critical CVE.\n\n"
        "## Implementation Steps\n"
        "1. Run `pip install --upgrade affected-package`\n"
        "2. Re-scan with the security tool.\n"
        "3. Deploy the fix.\n\n"
        "## Business Impact\n"
        "An unresolved critical CVE may block the release."
    ),
    confidence_score=0.85,
    source=ResponseSource.AI_GENERATED,
    latency_ms=450,
    model="gpt-4o-mini",
)
