"""Fixture factory functions for knowledge base retrieval tests (WO-067).

Generates realistic seed data for:
    - 5 services with varying health scores
    - 50+ findings across all severities and dimensions
    - 10+ policy rules
    - 5+ release assessments with decisions
    - User-service ownership mappings

Usage in tests:
    from tests.fixtures.knowledge_base_fixtures import (
        make_service,
        make_assessment,
        make_assessment_score,
        make_findings_batch,
        make_policy_with_rules,
        make_release_assessment,
        make_release_decision,
        KBFixtureBundle,
    )
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _uid() -> uuid.UUID:
    return uuid.uuid4()


# ---------------------------------------------------------------------------
# Service fixtures
# ---------------------------------------------------------------------------

def make_service(
    name: str = "test-service",
    description: str = "A test service",
    is_demo: bool = False,
) -> dict[str, Any]:
    return {
        "id": _uid(),
        "name": name,
        "description": description,
        "repository_url": f"https://github.com/org/{name}",
        "owner_team": "platform-team",
        "metadata": {"language": "python", "framework": "fastapi"},
        "is_demo": is_demo,
        "deleted_at": None,
        "created_at": _now(),
        "updated_at": _now(),
    }


def make_five_services() -> list[dict[str, Any]]:
    """Return 5 services with varying characteristics."""
    return [
        make_service("payment-service", "Core payment processing service"),
        make_service("auth-service", "Authentication and authorisation service"),
        make_service("notification-service", "Email and SMS notification service"),
        make_service("reporting-service", "Business reporting and analytics"),
        make_service("legacy-api", "Legacy API gateway (needs remediation)"),
    ]


# ---------------------------------------------------------------------------
# User fixtures
# ---------------------------------------------------------------------------

def make_user(role: str = "developer") -> dict[str, Any]:
    return {
        "id": _uid(),
        "email": f"{role}-{uuid.uuid4().hex[:6]}@test.example",
        "role": role,
        "is_active": True,
        "created_at": _now(),
    }


# ---------------------------------------------------------------------------
# Assessment fixtures
# ---------------------------------------------------------------------------

def make_assessment(
    service_id: uuid.UUID,
    assessment_type: str = "health_check",
    status: str = "completed",
    triggered_by: uuid.UUID | None = None,
) -> dict[str, Any]:
    return {
        "id": _uid(),
        "service_id": service_id,
        "assessment_type": assessment_type,
        "trigger_type": "manual",
        "triggered_by": triggered_by,
        "status": status,
        "collected_data": {"source": "test"},
        "started_at": _now(),
        "completed_at": _now() if status == "completed" else None,
        "created_at": _now(),
        "updated_at": _now(),
    }


def make_assessment_score(
    assessment_id: uuid.UUID,
    service_id: uuid.UUID,
    overall_score: float = 75.0,
    dimension_scores: dict[str, float] | None = None,
) -> dict[str, Any]:
    return {
        "id": _uid(),
        "assessment_id": assessment_id,
        "service_id": service_id,
        "score_type": "health",
        "overall_score": Decimal(str(overall_score)),
        "dimension_scores": dimension_scores or {
            "code_quality": 80.0,
            "test_coverage": 72.0,
            "security": 85.0,
            "documentation": 65.0,
            "operations_readiness": 78.0,
        },
        "contributing_factors": None,
        "weights_used": {
            "code_quality": 0.25,
            "test_coverage": 0.25,
            "security": 0.20,
            "documentation": 0.15,
            "operations_readiness": 0.15,
        },
        "created_at": _now(),
    }


# ---------------------------------------------------------------------------
# Finding fixtures
# ---------------------------------------------------------------------------

_SEVERITIES = ["critical", "high", "medium", "low"]
_DIMENSIONS = [
    "code_quality",
    "test_coverage",
    "security",
    "documentation",
    "operations_readiness",
]

_FINDING_TEMPLATES = [
    ("LOW_TEST_COVERAGE", "low", "test_coverage", "Test coverage is below threshold"),
    ("OUTDATED_DEPENDENCY", "medium", "security", "Dependency is outdated"),
    ("MISSING_README", "low", "documentation", "Service lacks a README"),
    ("CRITICAL_CVE", "critical", "security", "Critical CVE detected in dependency"),
    ("MISSING_HEALTH_CHECK", "medium", "operations_readiness", "No health endpoint"),
    ("NO_CI_CD_PIPELINE", "high", "operations_readiness", "No CI/CD pipeline"),
    ("WEAK_PASSWORD_POLICY", "high", "security", "Weak password policy"),
    ("MISSING_ERROR_HANDLING", "medium", "code_quality", "Missing error handling"),
    ("NO_MONITORING", "high", "operations_readiness", "No metrics endpoint"),
    ("INSECURE_DEPENDENCY", "high", "security", "Dependency with known CVE"),
]


def make_finding(
    service_id: uuid.UUID,
    assessment_id: uuid.UUID,
    policy_rule_id: uuid.UUID,
    severity: str = "high",
    dimension: str = "security",
    title: str = "Test finding",
    status: str = "open",
) -> dict[str, Any]:
    return {
        "id": _uid(),
        "assessment_id": assessment_id,
        "service_id": service_id,
        "policy_rule_id": policy_rule_id,
        "severity": severity,
        "escalation_required": severity == "critical",
        "dimension": dimension,
        "status": status,
        "title": title,
        "description": f"Detailed description for: {title}",
        "evidence": {"actual_value": 42, "threshold": 80},
        "ai_explanation": None,
        "confidence_score": Decimal("0.85"),
        "resolved_at": None,
        "created_at": _now(),
        "updated_at": _now(),
    }


def make_findings_batch(
    service_id: uuid.UUID,
    assessment_id: uuid.UUID,
    policy_rule_ids: list[uuid.UUID],
) -> list[dict[str, Any]]:
    """Generate 10 findings covering various severities and dimensions."""
    findings = []
    for i, (_, severity, dimension, title) in enumerate(_FINDING_TEMPLATES):
        rule_id = policy_rule_ids[i % len(policy_rule_ids)]
        findings.append(make_finding(
            service_id=service_id,
            assessment_id=assessment_id,
            policy_rule_id=rule_id,
            severity=severity,
            dimension=dimension,
            title=title,
        ))
    return findings


def make_remediation_recommendation(finding_id: uuid.UUID, source: str = "ai_generated") -> dict[str, Any]:
    return {
        "id": _uid(),
        "finding_id": finding_id,
        "recommendation_text": "Increase test coverage to at least 80% by adding unit tests.",
        "implementation_guide": "1. Run pytest --cov. 2. Identify gaps. 3. Write tests.",
        "business_impact": "Reduces regression risk by 40%.",
        "confidence_score": Decimal("0.90"),
        "source": source,
        "created_at": _now(),
    }


# ---------------------------------------------------------------------------
# Policy fixtures
# ---------------------------------------------------------------------------

def make_policy(
    service_id: uuid.UUID | None = None,
    dimension: str = "security",
    name: str = "Security Policy",
) -> dict[str, Any]:
    return {
        "id": _uid(),
        "service_id": service_id,
        "name": name,
        "dimension": dimension,
        "description": f"Policy for {dimension} compliance",
        "is_active": True,
        "version": 1,
        "created_by": None,
        "deleted_at": None,
        "created_at": _now(),
        "updated_at": _now(),
    }


def make_policy_rule(
    policy_id: uuid.UUID,
    name: str = "Test Rule",
    rule_type: str = "threshold_gte",
    severity: str = "high",
    weight: float = 1.0,
) -> dict[str, Any]:
    return {
        "id": _uid(),
        "policy_id": policy_id,
        "name": name,
        "rule_type": rule_type,
        "threshold_config": {"operator": "gte", "value": 80, "unit": "percent"},
        "severity": severity,
        "weight": Decimal(str(weight)),
        "is_active": True,
        "deleted_at": None,
        "created_at": _now(),
        "updated_at": _now(),
    }


def make_policy_with_rules(
    service_id: uuid.UUID | None = None,
    dimension: str = "test_coverage",
    num_rules: int = 3,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Return a (policy, rules_list) tuple."""
    policy = make_policy(service_id=service_id, dimension=dimension, name=f"{dimension} Policy")
    rules = [
        make_policy_rule(
            policy_id=policy["id"],
            name=f"{dimension} Rule {i + 1}",
            severity=_SEVERITIES[i % len(_SEVERITIES)],
        )
        for i in range(num_rules)
    ]
    return policy, rules


# ---------------------------------------------------------------------------
# Release assessment fixtures
# ---------------------------------------------------------------------------

def make_release_assessment(
    service_id: uuid.UUID,
    status: str = "completed",
    requested_by: uuid.UUID | None = None,
) -> dict[str, Any]:
    return {
        "id": _uid(),
        "service_id": service_id,
        "commit_sha": "abc123def456",
        "pr_reference": "https://github.com/org/repo/pull/42",
        "trigger_type": "manual",
        "requested_by": requested_by,
        "status": status,
        "change_analysis": {
            "files_changed": 12,
            "risk_factors": ["dependency_update", "security_module_change"],
        },
        "created_at": _now(),
        "completed_at": _now() if status == "completed" else None,
        "updated_at": _now(),
    }


def make_release_decision(
    release_assessment_id: uuid.UUID,
    decision: str = "APPROVE",
    decided_by: uuid.UUID | None = None,
    was_escalated: bool = False,
) -> dict[str, Any]:
    return {
        "id": _uid(),
        "release_assessment_id": release_assessment_id,
        "health_score_at_decision": Decimal("78.5"),
        "risk_score_at_decision": Decimal("25.0"),
        "decision": decision,
        "decided_by_role": "tech_lead",
        "decided_by": decided_by,
        "rationale": f"Decision: {decision}. All quality gates passed.",
        "comment": None,
        "was_escalated": was_escalated,
        "created_at": _now(),
    }


# ---------------------------------------------------------------------------
# Complete fixture bundle
# ---------------------------------------------------------------------------

@dataclass
class KBFixtureBundle:
    """Complete fixture dataset for knowledge base integration tests.

    Attributes:
        services:       5 test services.
        users:          One user per role.
        assessments:    One completed health_check per service.
        scores:         One AssessmentScore per assessment.
        findings:       10 findings per service (50 total).
        recommendations: One recommendation per finding.
        policies:       One policy per dimension × service (25 total).
        rules:          3 rules per policy (75+ total).
        release_assessments: 5+ release assessments across services.
        release_decisions:   4 release decisions (1 pending without decision).
    """

    services: list[dict[str, Any]] = field(default_factory=list)
    users: dict[str, dict[str, Any]] = field(default_factory=dict)
    assessments: list[dict[str, Any]] = field(default_factory=list)
    scores: list[dict[str, Any]] = field(default_factory=list)
    findings: list[dict[str, Any]] = field(default_factory=list)
    recommendations: list[dict[str, Any]] = field(default_factory=list)
    policies: list[dict[str, Any]] = field(default_factory=list)
    rules: list[dict[str, Any]] = field(default_factory=list)
    release_assessments: list[dict[str, Any]] = field(default_factory=list)
    release_decisions: list[dict[str, Any]] = field(default_factory=list)


def build_kb_fixture_bundle() -> KBFixtureBundle:
    """Build a complete knowledge base fixture dataset."""
    bundle = KBFixtureBundle()

    # Users
    for role in ["developer", "tech_lead", "security_reviewer", "platform_admin", "engineering_manager"]:
        bundle.users[role] = make_user(role)

    # Services
    bundle.services = make_five_services()

    for i, service in enumerate(bundle.services):
        svc_id = service["id"]

        # Assessment
        assessment = make_assessment(
            service_id=svc_id,
            triggered_by=bundle.users["developer"]["id"],
        )
        bundle.assessments.append(assessment)

        # Score (varying health scores)
        score = make_assessment_score(
            assessment_id=assessment["id"],
            service_id=svc_id,
            overall_score=55.0 + i * 10,  # 55, 65, 75, 85, 95
        )
        bundle.scores.append(score)

        # Policies & rules (one per dimension)
        service_rules: list[dict[str, Any]] = []
        for dimension in _DIMENSIONS:
            policy, rules = make_policy_with_rules(
                service_id=svc_id,
                dimension=dimension,
                num_rules=3,
            )
            bundle.policies.append(policy)
            bundle.rules.extend(rules)
            service_rules.extend(rules)

        # Findings (10 per service using the rules)
        rule_ids = [r["id"] for r in service_rules]
        findings = make_findings_batch(
            service_id=svc_id,
            assessment_id=assessment["id"],
            policy_rule_ids=rule_ids,
        )
        bundle.findings.extend(findings)

        # Recommendations (one per finding)
        for finding in findings:
            rec = make_remediation_recommendation(finding_id=finding["id"])
            bundle.recommendations.append(rec)

        # Release assessments & decisions
        release = make_release_assessment(
            service_id=svc_id,
            requested_by=bundle.users["developer"]["id"],
        )
        bundle.release_assessments.append(release)

        # Last service gets a pending decision (no decision yet)
        if i < 4:
            decision_outcome = ["APPROVE", "APPROVE", "CONDITIONAL_APPROVE", "BLOCK"][i]
            rd = make_release_decision(
                release_assessment_id=release["id"],
                decision=decision_outcome,
                decided_by=bundle.users["tech_lead"]["id"],
                was_escalated=(decision_outcome == "BLOCK"),
            )
            bundle.release_decisions.append(rd)
        # service[4] has no decision — tests the "pending" path.

    return bundle
