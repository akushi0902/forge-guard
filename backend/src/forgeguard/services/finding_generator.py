"""Finding generation service (WO-041).

Transforms FAIL/ERROR RuleEvaluationResult objects into persistent Finding
records.  Duplicate open findings (same service + policy_rule_id) are updated
rather than duplicated.  Critical security findings are auto-flagged for
escalation via SeverityClassifier.
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog

from forgeguard.data.repositories.findings import FindingRepository
from forgeguard.services.domain.evaluation import EvaluationStatus, RuleEvaluationResult
from forgeguard.services.domain.severity import SeverityClassifier, SeverityLevel

logger = structlog.get_logger(__name__)

_ACTIONABLE = frozenset({EvaluationStatus.FAIL, EvaluationStatus.ERROR})


class FindingGenerator:
    """Orchestrates finding creation from rule evaluation results.

    Stateless beyond the injected repository — one instance per request
    is fine; there is no per-instance mutable state.
    """

    def __init__(self, repository: FindingRepository) -> None:
        self._repo = repository

    async def generate_findings(
        self,
        results: list[RuleEvaluationResult],
        assessment_id: uuid.UUID,
        service_id: uuid.UUID,
    ) -> list[dict[str, Any]]:
        """Convert FAIL/ERROR results into Finding records.

        For each actionable result:
          - If an open finding already exists for (service_id, policy_rule_id),
            update its evidence and assessment_id.
          - Otherwise create a new Finding with status='open'.

        PASS and INCONCLUSIVE results are ignored.

        Returns the list of created/updated finding dicts.
        """
        findings: list[dict[str, Any]] = []

        for result in results:
            if result.status not in _ACTIONABLE:
                continue

            existing = await self._repo.find_existing_open_finding(
                service_id, result.rule_id
            )

            if existing is not None:
                updated = await self._repo.update(
                    existing["id"],
                    {
                        "assessment_id": assessment_id,
                        "evidence": self._build_evidence(result),
                    },
                )
                if updated is not None:
                    findings.append(updated)
                    logger.info(
                        "finding_generator.finding_updated",
                        finding_id=str(existing["id"]),
                        rule_id=str(result.rule_id),
                        service_id=str(service_id),
                    )
            else:
                escalation = SeverityClassifier.is_escalation_required(
                    result.severity, result.dimension
                )
                severity_value = (
                    result.severity.value
                    if isinstance(result.severity, SeverityLevel)
                    else str(result.severity)
                )
                finding_data: dict[str, Any] = {
                    "id": uuid.uuid4(),
                    "assessment_id": assessment_id,
                    "service_id": service_id,
                    "policy_rule_id": result.rule_id,
                    "severity": severity_value,
                    "dimension": result.dimension,
                    "status": "open",
                    "title": self._make_title(result),
                    "description": self._make_description(result),
                    "evidence": self._build_evidence(result),
                    "escalation_required": escalation,
                }
                new_finding = await self._repo.create(finding_data)
                findings.append(new_finding)
                logger.info(
                    "finding_generator.finding_created",
                    finding_id=str(finding_data["id"]),
                    rule_id=str(result.rule_id),
                    severity=severity_value,
                    escalation_required=escalation,
                )

        return findings

    @staticmethod
    def _make_title(result: RuleEvaluationResult) -> str:
        return f"{result.rule_name} violation in {result.dimension}"

    @staticmethod
    def _make_description(result: RuleEvaluationResult) -> str:
        if result.status == EvaluationStatus.ERROR:
            return (
                f"Rule evaluation error for {result.rule_name}: "
                "evaluation did not complete successfully"
            )
        return (
            f"Expected {result.expected_value} but found {result.actual_value} "
            f"for {result.rule_name}"
        )

    @staticmethod
    def _build_evidence(result: RuleEvaluationResult) -> dict[str, Any]:
        return {
            **result.evidence,
            "actual_value": result.actual_value,
            "expected_value": result.expected_value,
            "evaluation_status": result.status.value,
        }
