"""CombinedDecisionViewService — aggregate decision context for a release assessment (WO-052).

Orchestrates data retrieval from multiple repositories, computes the current
system recommendation, groups findings by severity, derives conditions for
conditional approvals, and assembles the CombinedDecisionViewResponse.
"""

from __future__ import annotations

import json
import uuid
from decimal import Decimal
from typing import Any, Optional

import structlog

from forgeguard.api.schemas.release_decision_view import (
    AssessmentMetadata,
    CombinedDecisionViewResponse,
    ConditionItem,
    ContributingFactor,
    DecisionRecord,
    DimensionBreakdown,
    EscalationInfo,
    FindingItem,
    FindingsSummary,
    HealthScoreBreakdown,
    RiskScoreBreakdown,
    SeverityGroup,
    SystemRecommendation,
)
from forgeguard.services.decision_engine.engine import DecisionEngine, DecisionOutcome
from forgeguard.services.decision_engine.escalation_service import SecurityEscalationService

logger = structlog.get_logger(__name__)

# Maximum findings returned per severity group before truncation.
_MAX_PER_SEVERITY = 50

_SEVERITY_ORDER = ("critical", "high", "medium", "low")


def _parse_jsonb(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return {}
    return value or {}


def _build_health_breakdown(score_row: dict[str, Any]) -> HealthScoreBreakdown:
    overall = float(score_row.get("overall_score") or 0)
    raw_dims = _parse_jsonb(score_row.get("dimension_scores"))
    dimensions: list[DimensionBreakdown] = []
    if isinstance(raw_dims, dict):
        for name, ds in raw_dims.items():
            if isinstance(ds, dict):
                dimensions.append(
                    DimensionBreakdown(
                        name=name,
                        score=float(ds.get("score") or 0),
                        rule_count=int(ds.get("total_rules") or 0),
                        pass_count=int(ds.get("passed_rules") or 0),
                    )
                )
    return HealthScoreBreakdown(overall=overall, dimensions=dimensions)


def _build_risk_breakdown(score_row: dict[str, Any]) -> RiskScoreBreakdown:
    overall = float(score_row.get("overall_score") or 0)
    raw_factors = _parse_jsonb(score_row.get("contributing_factors"))
    factors: list[ContributingFactor] = []
    if isinstance(raw_factors, list):
        for f in raw_factors:
            if isinstance(f, dict):
                factors.append(
                    ContributingFactor(
                        factor=str(f.get("metric_name") or f.get("factor") or ""),
                        impact=str(f.get("risk_contribution") or f.get("impact") or ""),
                        weight=float(f.get("weight") or 0),
                    )
                )
    return RiskScoreBreakdown(overall=overall, contributing_factors=factors)


def _findings_from_change_analysis(change_analysis: Any) -> list[dict[str, Any]]:
    """Extract raw finding dicts from change_analysis JSONB."""
    parsed = _parse_jsonb(change_analysis)
    if isinstance(parsed, dict):
        return parsed.get("findings") or []
    return []


def _build_finding_item(f: dict[str, Any]) -> Optional[FindingItem]:
    raw_id = f.get("id")
    if not raw_id:
        return None
    try:
        fid = uuid.UUID(str(raw_id))
    except (ValueError, AttributeError):
        return None
    return FindingItem(
        id=fid,
        title=f.get("title") or "",
        severity=f.get("severity") or "",
        dimension=f.get("dimension") or "",
        explanation=f.get("explanation") or f.get("ai_explanation"),
        business_impact=f.get("business_impact"),
        remediation_steps=f.get("remediation_steps") or [],
        confidence_score=float(f.get("confidence_score") or 0),
        source=f.get("source"),
    )


def _group_findings_by_severity(
    raw_findings: list[dict[str, Any]],
) -> tuple[FindingsSummary, list[dict[str, Any]]]:
    """Group raw finding dicts by severity; truncate at _MAX_PER_SEVERITY each group.

    Returns (FindingsSummary, flat_list_of_raw_findings_for_escalation_check).
    """
    groups: dict[str, list[FindingItem]] = {s: [] for s in _SEVERITY_ORDER}
    all_raw: list[dict[str, Any]] = []

    for f in raw_findings:
        item = _build_finding_item(f)
        if item is None:
            continue
        sev = item.severity.lower()
        all_raw.append(f)
        if sev in groups and len(groups[sev]) < _MAX_PER_SEVERITY:
            groups[sev].append(item)
        elif sev not in groups:
            pass  # unknown severity skipped

    total = len(all_raw)
    by_severity: dict[str, SeverityGroup] = {}
    for sev in _SEVERITY_ORDER:
        by_severity[sev] = SeverityGroup(count=len(groups[sev]), items=groups[sev])

    # Recompute counts including those truncated above _MAX_PER_SEVERITY
    raw_counts: dict[str, int] = {s: 0 for s in _SEVERITY_ORDER}
    for f in raw_findings:
        sev = (f.get("severity") or "").lower()
        if sev in raw_counts:
            raw_counts[sev] += 1

    for sev in _SEVERITY_ORDER:
        by_severity[sev] = SeverityGroup(count=raw_counts[sev], items=groups[sev])

    return FindingsSummary(total=total, by_severity=by_severity), all_raw


def _derive_conditions(
    raw_findings: list[dict[str, Any]],
) -> list[ConditionItem]:
    """Derive actionable conditions from HIGH severity findings for CONDITIONAL_APPROVE."""
    conditions: list[ConditionItem] = []
    for f in raw_findings:
        if (f.get("severity") or "").lower() == "high":
            raw_id = f.get("id")
            try:
                fid = uuid.UUID(str(raw_id))
            except (ValueError, AttributeError, TypeError):
                continue
            title = f.get("title") or "High severity finding"
            dimension = f.get("dimension") or "unknown"
            conditions.append(
                ConditionItem(
                    condition=f"Resolve high severity finding in '{dimension}' dimension: {title}",
                    source_finding_id=fid,
                )
            )
    return conditions


class CombinedDecisionViewService:
    """Orchestrates data retrieval and assembles the combined decision view.

    Args:
        assessment_repo: ReleaseAssessmentRepository instance.
        score_repo:      AssessmentScoreRepository instance.
        decision_repo:   DecisionRepository instance.
    """

    def __init__(
        self,
        assessment_repo: Any,
        score_repo: Any,
        decision_repo: Any,
    ) -> None:
        self._assessment_repo = assessment_repo
        self._score_repo = score_repo
        self._decision_repo = decision_repo

    async def get_combined_view(
        self, assessment_id: uuid.UUID
    ) -> CombinedDecisionViewResponse | None:
        """Assemble the complete decision view for an assessment.

        Returns None when the assessment does not exist (caller should 404).
        Raises no exceptions — all missing data produces partial/default fields.
        """
        # 1. Load assessment
        assessment = await self._assessment_repo.get_by_id(assessment_id)
        if assessment is None:
            return None

        # 2. Fetch health and risk scores concurrently (sequential fallback)
        health_row = await self._score_repo.get_score_by_type(assessment_id, "health")
        risk_row = await self._score_repo.get_score_by_type(assessment_id, "risk")

        # 3. Fetch most recent human decision (if any)
        decisions = await self._decision_repo.find_by_release_assessment(assessment_id)
        latest_decision = decisions[-1] if decisions else None

        # 4. Build score breakdowns
        health_breakdown: Optional[HealthScoreBreakdown] = None
        risk_breakdown: Optional[RiskScoreBreakdown] = None
        scoring_incomplete = False
        scoring_incomplete_reason: Optional[str] = None

        if health_row:
            health_breakdown = _build_health_breakdown(health_row)
        if risk_row:
            risk_breakdown = _build_risk_breakdown(risk_row)

        if not health_row and not risk_row:
            scoring_incomplete = True
            scoring_incomplete_reason = "Neither health nor risk score has been computed"
        elif not health_row:
            scoring_incomplete = True
            scoring_incomplete_reason = "Health score not yet computed"
        elif not risk_row:
            scoring_incomplete = True
            scoring_incomplete_reason = "Risk score not yet computed"

        # 5. Extract findings from change_analysis JSONB
        raw_findings = _findings_from_change_analysis(assessment.get("change_analysis"))
        findings_summary, all_raw = _group_findings_by_severity(raw_findings)

        # 6. Compute system recommendation
        if health_row and risk_row:
            health_d = Decimal(str(health_row.get("overall_score") or 0))
            risk_d = Decimal(str(risk_row.get("overall_score") or 0))
        else:
            # No scores yet — default to BLOCK
            health_d = Decimal("0")
            risk_d = Decimal("100")

        threshold_decision = DecisionEngine.merge_scores(health_d, risk_d)
        escalation = SecurityEscalationService.check_escalation(all_raw, threshold_decision)

        system_rec = SystemRecommendation(
            decision=escalation.final_recommendation.value,
            threshold_config_id=threshold_decision.threshold_config_id,
            threshold_config_name=None,
        )

        # 7. Escalation info
        escalation_info = EscalationInfo(
            is_escalated=escalation.should_escalate,
            reasons=escalation.escalation_reasons if escalation.should_escalate else None,
        )

        # 8. Conditions (only for CONDITIONAL_APPROVE)
        conditions: Optional[list[ConditionItem]] = None
        if escalation.final_recommendation == DecisionOutcome.CONDITIONAL_APPROVE:
            conditions = _derive_conditions(all_raw)

        # 9. Build decision record if present
        decision_record: Optional[DecisionRecord] = None
        if latest_decision:
            try:
                created_at = latest_decision.get("created_at")
                from datetime import datetime, timezone  # noqa: PLC0415
                if created_at is None:
                    created_at = datetime.now(timezone.utc)
                decided_by_raw = latest_decision.get("decided_by")
                decided_by_uuid: Optional[uuid.UUID] = None
                if decided_by_raw:
                    decided_by_uuid = uuid.UUID(str(decided_by_raw))
                decision_record = DecisionRecord(
                    id=uuid.UUID(str(latest_decision["id"])),
                    decided_by=decided_by_uuid,
                    decided_by_role=latest_decision.get("decided_by_role"),
                    decision=latest_decision.get("decision") or "",
                    rationale=latest_decision.get("rationale"),
                    comment=latest_decision.get("comment"),
                    was_escalated=bool(latest_decision.get("was_escalated", False)),
                    created_at=created_at,
                )
            except Exception:
                logger.warning(
                    "decision_view_service.decision_record_parse_failed",
                    assessment_id=str(assessment_id),
                )

        # 10. Build assessment metadata
        metadata = AssessmentMetadata(
            id=uuid.UUID(str(assessment["id"])),
            service_id=uuid.UUID(str(assessment["service_id"])),
            commit_sha=assessment.get("commit_sha"),
            pr_reference=assessment.get("pr_reference"),
            status=assessment.get("status") or "unknown",
            created_at=assessment["created_at"],
            completed_at=assessment.get("completed_at"),
        )

        logger.info(
            "decision_view_service.view_assembled",
            assessment_id=str(assessment_id),
            recommendation=system_rec.decision,
            was_escalated=escalation_info.is_escalated,
            total_findings=findings_summary.total,
        )

        return CombinedDecisionViewResponse(
            assessment=metadata,
            system_recommendation=system_rec,
            health_score=health_breakdown,
            risk_score=risk_breakdown,
            findings_summary=findings_summary,
            escalation=escalation_info,
            conditions=conditions,
            decision_record=decision_record,
            scoring_incomplete=scoring_incomplete,
            scoring_incomplete_reason=scoring_incomplete_reason,
        )
