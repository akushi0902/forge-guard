"""Seed data: 10 prompt templates covering all 5 dimensions and 2+ severity levels.

Usage (standalone):
    python -m forgeguard.data.seeds.prompt_templates

The seed script is idempotent: it checks for existing templates by name+version
before inserting so it is safe to run multiple times.

Covered dimensions and severities:
    code_quality        — critical, high
    test_coverage       — high, medium
    security            — critical, high
    documentation       — medium, low
    operations_readiness— high, medium
"""

from __future__ import annotations

import asyncio
from typing import Any

_SEED_TEMPLATES: list[dict[str, Any]] = [
    # ------------------------------------------------------------------
    # code_quality
    # ------------------------------------------------------------------
    {
        "name": "code_quality_critical_review",
        "template_text": (
            "You are a senior software engineer reviewing a critical code quality finding.\n\n"
            "Service: $service_name\n"
            "Finding: $finding_title\n"
            "Severity: CRITICAL\n"
            "Dimension: Code Quality\n\n"
            "Evidence:\n$evidence\n\n"
            "Policy rule: $policy_rule_description\n\n"
            "This finding is CRITICAL and blocks release. Provide:\n"
            "1. Root cause analysis (2-3 sentences).\n"
            "2. Three specific, ordered remediation steps.\n"
            "3. Verification steps the reviewer should check after remediation.\n"
            "4. Estimated effort per step (low/medium/high).\n"
        ),
        "variables": {
            "service_name": "str",
            "finding_title": "str",
            "evidence": "str",
            "policy_rule_description": "str",
        },
        "dimension": "code_quality",
        "severity_level": "critical",
    },
    {
        "name": "code_quality_high_review",
        "template_text": (
            "You are reviewing a high-severity code quality finding for $service_name.\n\n"
            "Finding: $finding_title\n"
            "Evidence: $evidence\n"
            "Policy rule: $policy_rule_description\n\n"
            "Provide:\n"
            "1. A clear explanation of the quality risk.\n"
            "2. Two to three actionable remediation steps.\n"
            "3. Whether this finding should block the release or can be deferred.\n"
        ),
        "variables": {
            "service_name": "str",
            "finding_title": "str",
            "evidence": "str",
            "policy_rule_description": "str",
        },
        "dimension": "code_quality",
        "severity_level": "high",
    },
    # ------------------------------------------------------------------
    # test_coverage
    # ------------------------------------------------------------------
    {
        "name": "test_coverage_high_review",
        "template_text": (
            "You are a QA engineer reviewing a test coverage finding.\n\n"
            "Service: $service_name\n"
            "Finding: $finding_title\n"
            "Current coverage: $actual_value\n"
            "Required threshold: $threshold_value\n"
            "Evidence: $evidence\n\n"
            "Provide:\n"
            "1. Identify the highest-risk uncovered code paths.\n"
            "2. Three specific test cases that should be added.\n"
            "3. Whether this coverage gap represents a release blocker.\n"
        ),
        "variables": {
            "service_name": "str",
            "finding_title": "str",
            "actual_value": "str",
            "threshold_value": "str",
            "evidence": "str",
        },
        "dimension": "test_coverage",
        "severity_level": "high",
    },
    {
        "name": "test_coverage_medium_review",
        "template_text": (
            "A medium-severity test coverage gap was found in $service_name.\n\n"
            "Finding: $finding_title\n"
            "Evidence: $evidence\n"
            "Policy rule: $policy_rule_description\n\n"
            "Provide:\n"
            "1. Summary of missing coverage and its risk.\n"
            "2. Suggested unit tests to close the gap.\n"
            "3. A recommended timeline for remediation.\n"
        ),
        "variables": {
            "service_name": "str",
            "finding_title": "str",
            "evidence": "str",
            "policy_rule_description": "str",
        },
        "dimension": "test_coverage",
        "severity_level": "medium",
    },
    # ------------------------------------------------------------------
    # security
    # ------------------------------------------------------------------
    {
        "name": "security_critical_finding",
        "template_text": (
            "CRITICAL SECURITY FINDING — immediate action required.\n\n"
            "Service: $service_name\n"
            "Finding: $finding_title\n"
            "Evidence: $evidence\n"
            "Policy rule: $policy_rule_description\n\n"
            "This finding MUST be resolved before release. Provide:\n"
            "1. Attack vector and potential impact (1-2 sentences).\n"
            "2. Immediate mitigation steps (can be applied without code changes).\n"
            "3. Permanent fix steps.\n"
            "4. Verification command or test to confirm the fix.\n"
            "5. Whether the finding should trigger a security incident.\n"
        ),
        "variables": {
            "service_name": "str",
            "finding_title": "str",
            "evidence": "str",
            "policy_rule_description": "str",
        },
        "dimension": "security",
        "severity_level": "critical",
    },
    {
        "name": "security_high_finding",
        "template_text": (
            "A high-severity security finding was detected in $service_name.\n\n"
            "Finding: $finding_title\n"
            "Evidence: $evidence\n"
            "Policy: $policy_rule_description\n\n"
            "Provide:\n"
            "1. Explanation of the security risk in non-technical terms.\n"
            "2. Three remediation steps ordered by priority.\n"
            "3. Recommended testing to verify the fix.\n"
        ),
        "variables": {
            "service_name": "str",
            "finding_title": "str",
            "evidence": "str",
            "policy_rule_description": "str",
        },
        "dimension": "security",
        "severity_level": "high",
    },
    # ------------------------------------------------------------------
    # documentation
    # ------------------------------------------------------------------
    {
        "name": "documentation_medium_gap",
        "template_text": (
            "A documentation gap was identified in $service_name.\n\n"
            "Finding: $finding_title\n"
            "Evidence: $evidence\n"
            "Policy rule: $policy_rule_description\n\n"
            "Provide:\n"
            "1. Description of what documentation is missing or outdated.\n"
            "2. Template or outline for the required documentation.\n"
            "3. Recommended owner and deadline.\n"
        ),
        "variables": {
            "service_name": "str",
            "finding_title": "str",
            "evidence": "str",
            "policy_rule_description": "str",
        },
        "dimension": "documentation",
        "severity_level": "medium",
    },
    {
        "name": "documentation_low_gap",
        "template_text": (
            "A low-severity documentation finding was detected in $service_name.\n\n"
            "Finding: $finding_title\n"
            "Policy rule: $policy_rule_description\n\n"
            "Provide a brief recommendation for improving the documentation "
            "quality in one to two sentences, and suggest a suitable owner.\n"
        ),
        "variables": {
            "service_name": "str",
            "finding_title": "str",
            "policy_rule_description": "str",
        },
        "dimension": "documentation",
        "severity_level": "low",
    },
    # ------------------------------------------------------------------
    # operations_readiness
    # ------------------------------------------------------------------
    {
        "name": "operations_readiness_high",
        "template_text": (
            "A high-severity operations readiness finding was detected for $service_name.\n\n"
            "Finding: $finding_title\n"
            "Evidence: $evidence\n"
            "Policy rule: $policy_rule_description\n\n"
            "Provide:\n"
            "1. Explanation of the operational risk.\n"
            "2. Pre-release checklist items to address this finding.\n"
            "3. Runbook additions the on-call team should make.\n"
            "4. Monitoring or alerting recommendations.\n"
        ),
        "variables": {
            "service_name": "str",
            "finding_title": "str",
            "evidence": "str",
            "policy_rule_description": "str",
        },
        "dimension": "operations_readiness",
        "severity_level": "high",
    },
    {
        "name": "operations_readiness_medium",
        "template_text": (
            "An operations readiness gap was found in $service_name.\n\n"
            "Finding: $finding_title\n"
            "Evidence: $evidence\n"
            "Policy: $policy_rule_description\n\n"
            "Provide:\n"
            "1. Summary of the readiness gap.\n"
            "2. Two to three specific actions to close the gap before release.\n"
            "3. Recommended monitoring to detect related incidents post-release.\n"
        ),
        "variables": {
            "service_name": "str",
            "finding_title": "str",
            "evidence": "str",
            "policy_rule_description": "str",
        },
        "dimension": "operations_readiness",
        "severity_level": "medium",
    },
]


async def seed_prompt_templates(session_factory) -> int:
    """Insert seed templates that do not yet exist in the database.

    Args:
        session_factory: An ``async_sessionmaker`` or async context manager
                         factory returning an ``AsyncSession``.

    Returns:
        Number of templates actually inserted (skips existing name+version rows).
    """
    from forgeguard.data.repositories.prompt_template_repository import (  # noqa: PLC0415
        PromptTemplateRepository,
    )

    inserted = 0
    async with session_factory() as session:
        repo = PromptTemplateRepository(session)
        for tpl_data in _SEED_TEMPLATES:
            existing = await repo.get_by_name_and_version(tpl_data["name"], 1)
            if existing is not None:
                continue
            await repo.create(
                name=tpl_data["name"],
                template_text=tpl_data["template_text"],
                variables=tpl_data["variables"],
                dimension=tpl_data["dimension"],
                severity_level=tpl_data["severity_level"],
                created_by=None,
            )
            inserted += 1
        await session.commit()
    return inserted


if __name__ == "__main__":  # pragma: no cover
    import logging

    logging.basicConfig(level=logging.INFO)
    log = logging.getLogger(__name__)

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from forgeguard.core.config import get_settings

    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    count = asyncio.run(seed_prompt_templates(factory))
    log.info("Seeded %d prompt templates.", count)
