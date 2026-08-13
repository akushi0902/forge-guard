"""Assessments domain SQLAlchemy ORM models.

Tables defined here persist the complete DETECT → EXPLAIN → RECOMMEND →
REMEDIATE → VALIDATE → RE-SCORE → APPROVE/BLOCK governance lifecycle:

    Assessment        — a single health or release-risk evaluation run
    AssessmentScore   — computed overall + dimension breakdown scores
    Finding           — a policy violation detected during an assessment
    ReleaseAssessment — a release readiness check for a specific commit/PR
    ReleaseDecision   — immutable approve/block record (no updated_at, no UPDATE)

Design constraints:
    - VARCHAR + CHECK constraint for status/type/severity/decision — no PG ENUMs.
    - JSONB for dimension_scores, evidence, ai_explanation, change_analysis.
    - DECIMAL(5,2) with CHECK(0 ≤ score ≤ 100) for all score columns.
    - ReleaseDecision is append-only — no updated_at column, no UPDATE privilege.
    - All TIMESTAMPTZ columns.
    - Soft-delete NOT used here — assessments are retained per data-retention
      policy (180 days for scores/findings, 365 days for release_decisions).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from forgeguard.services.domain.severity import SeverityLevel

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from forgeguard.data.models import Base

# ---------------------------------------------------------------------------
# Valid values — kept in sync with CHECK constraints below.
# ---------------------------------------------------------------------------

VALID_ASSESSMENT_TYPES: tuple[str, ...] = ("health_check", "release_risk")
VALID_TRIGGER_TYPES: tuple[str, ...] = ("manual", "scheduled", "webhook")
VALID_ASSESSMENT_STATUSES: tuple[str, ...] = (
    "pending",
    "in_progress",
    "completed",
    "failed",
)
VALID_FINDING_STATUSES: tuple[str, ...] = (
    "open",
    "acknowledged",
    "remediated",
    "exception_granted",
    "reopened",
)
VALID_SEVERITIES: tuple[str, ...] = ("critical", "high", "medium", "low")
VALID_DIMENSIONS: tuple[str, ...] = (
    "code_quality",
    "test_coverage",
    "security",
    "documentation",
    "operations_readiness",
)
VALID_DECISIONS: tuple[str, ...] = ("APPROVE", "CONDITIONAL_APPROVE", "BLOCK")

_ASSESSMENT_TYPE_CHECK = (
    "assessment_type IN ('health_check','release_risk')"
)
_TRIGGER_TYPE_CHECK = (
    "trigger_type IN ('manual','scheduled','webhook')"
)
_ASSESSMENT_STATUS_CHECK = (
    "status IN ('pending','in_progress','completed','failed')"
)
_FINDING_STATUS_CHECK = (
    "status IN ('open','acknowledged','remediated','exception_granted','reopened')"
)
_SEVERITY_CHECK = (
    "severity IN ('critical','high','medium','low')"
)
_DIMENSION_CHECK = (
    "dimension IN ("
    "'code_quality','test_coverage','security',"
    "'documentation','operations_readiness'"
    ")"
)
_DECISION_CHECK = (
    "decision IN ('APPROVE','CONDITIONAL_APPROVE','BLOCK')"
)
_SCORE_RANGE_CHECK = "overall_score >= 0 AND overall_score <= 100"
_HEALTH_SCORE_RANGE_CHECK = (
    "health_score_at_decision >= 0 AND health_score_at_decision <= 100"
)
_RISK_SCORE_RANGE_CHECK = (
    "risk_score_at_decision >= 0 AND risk_score_at_decision <= 100"
)
_CONFIDENCE_RANGE_CHECK = (
    "confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)"
)


class Assessment(Base):
    """A single governance evaluation run (health check or release risk).

    Column notes:
        assessment_type  — health_check: periodic Policy Guardian evaluation.
                           release_risk: on-demand Release Guardian evaluation.
        trigger_type     — how the assessment was initiated.
        status           — lifecycle state; failed assessments retain started_at
                           but have NULL completed_at.
        collected_data   — JSONB snapshot of inputs fed to the scoring engine.
    """

    __tablename__ = "assessments"
    __table_args__ = (
        CheckConstraint(_ASSESSMENT_TYPE_CHECK, name="valid_assessment_type"),
        CheckConstraint(_TRIGGER_TYPE_CHECK, name="valid_trigger_type"),
        CheckConstraint(_ASSESSMENT_STATUS_CHECK, name="valid_assessment_status"),
        Index("ix_assessments_service_id_created_at", "service_id", "created_at"),
        Index("ix_assessments_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    service_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("services.id", ondelete="CASCADE"),
        nullable=False,
    )
    assessment_type: Mapped[str] = mapped_column(String(50), nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(50), nullable=False)
    triggered_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    collected_data: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONB, nullable=True
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    scores: Mapped[list[AssessmentScore]] = relationship(
        "AssessmentScore",
        back_populates="assessment",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    findings: Mapped[list[Finding]] = relationship(
        "Finding",
        back_populates="assessment",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class AssessmentScore(Base):
    """Computed scores for a single assessment run.

    Column notes:
        score_type       — 'health' or 'risk'; not enum-constrained to allow
                           future score types without migration.
        overall_score    — DECIMAL(5,2) with 0-100 CHECK; the main scalar result.
        dimension_scores — JSONB: {"code_quality": 85.0, "test_coverage": 72.0,
                           "security": 90.0, "documentation": 65.0,
                           "operations_readiness": 78.0}
        contributing_factors — JSONB: AI-generated context; NULL when AI unavailable.
    """

    __tablename__ = "assessment_scores"
    __table_args__ = (
        CheckConstraint(_SCORE_RANGE_CHECK, name="valid_score_range"),
        Index(
            "ix_assessment_scores_service_id_score_type_created_at",
            "service_id",
            "score_type",
            "created_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    assessment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assessments.id", ondelete="CASCADE"),
        nullable=False,
    )
    service_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("services.id", ondelete="CASCADE"),
        nullable=False,
    )
    score_type: Mapped[str] = mapped_column(String(50), nullable=False)
    overall_score: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 2), nullable=True
    )
    dimension_scores: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    contributing_factors: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONB, nullable=True
    )
    weights_used: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="'{}'"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    assessment: Mapped[Assessment] = relationship(
        "Assessment", back_populates="scores"
    )


class Finding(Base):
    """A policy violation detected during a governance assessment.

    Column notes:
        severity         — critical/high/medium/low; CHECK constrained.
        dimension        — which engineering dimension the rule belongs to.
        status           — suppressed means an approved exception is active.
        evidence         — JSONB raw data that triggered the finding.
        ai_explanation   — JSONB AI-generated explanation; NULL when AI unavailable.
        confidence_score — DECIMAL(3,2) AI confidence 0.00–1.00; NULL allowed.
        resolved_at      — NULL for open/in_progress/suppressed findings.
    """

    __tablename__ = "findings"
    __table_args__ = (
        CheckConstraint(_SEVERITY_CHECK, name="valid_severity"),
        CheckConstraint(_DIMENSION_CHECK, name="valid_dimension"),
        CheckConstraint(_FINDING_STATUS_CHECK, name="valid_finding_status"),
        CheckConstraint(_CONFIDENCE_RANGE_CHECK, name="valid_confidence_score"),
        # Primary dashboard query: all open critical findings for a service
        Index(
            "ix_findings_service_id_severity_status",
            "service_id",
            "severity",
            "status",
        ),
        # Assessment detail view: findings grouped by assessment and severity
        Index("ix_findings_assessment_id_severity", "assessment_id", "severity"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    assessment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assessments.id", ondelete="CASCADE"),
        nullable=False,
    )
    service_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("services.id", ondelete="CASCADE"),
        nullable=False,
    )
    policy_rule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("policy_rules.id", ondelete="RESTRICT"),
        nullable=False,
    )
    severity: Mapped[SeverityLevel] = mapped_column(String(20), nullable=False)
    escalation_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    dimension: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="open", server_default="'open'"
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    evidence: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    ai_explanation: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONB, nullable=True
    )
    confidence_score: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(3, 2), nullable=True
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    assessment: Mapped[Assessment] = relationship(
        "Assessment", back_populates="findings"
    )


class ReleaseAssessment(Base):
    """A release readiness check for a specific commit SHA or PR reference.

    Column notes:
        commit_sha     — short or full SHA of the commit being assessed.
        pr_reference   — GitHub PR URL or number; may coexist with commit_sha.
        change_analysis — JSONB: AI-generated risk analysis of the diff.
        completed_at   — NULL for pending/in_progress assessments.
    """

    __tablename__ = "release_assessments"
    __table_args__ = (
        CheckConstraint(_ASSESSMENT_STATUS_CHECK, name="valid_release_assessment_status"),
        Index(
            "ix_release_assessments_service_id_created_at",
            "service_id",
            "created_at",
        ),
        Index("ix_release_assessments_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    service_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("services.id", ondelete="CASCADE"),
        nullable=False,
    )
    commit_sha: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    pr_reference: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    trigger_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default="manual", server_default="'manual'"
    )
    requested_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="pending", server_default="'pending'"
    )
    change_analysis: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONB, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    decision: Mapped[Optional[ReleaseDecision]] = relationship(
        "ReleaseDecision",
        back_populates="release_assessment",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class ReleaseDecision(Base):
    """Immutable approve/block decision for a release assessment.

    IMPORTANT: This table is append-only.
        - No updated_at column (immutability enforced at schema level).
        - The application role must not be granted UPDATE privilege on this table.
        - was_escalated=True when a critical security finding auto-routed to
          the Security Reviewer role, bypassing normal thresholds.

    Column notes:
        health_score_at_decision — DECIMAL(5,2) health score captured at the
                                   moment of decision (score may change later).
        risk_score_at_decision   — DECIMAL(5,2) risk score at decision time.
        decision                 — APPROVE / CONDITIONAL_APPROVE / BLOCK.
        decided_by_role          — role name of the deciding user (denormalised
                                   for audit durability; role can change later).
        rationale                — required explanation for the decision.
        comment                  — optional additional context.
    """

    __tablename__ = "release_decisions"
    __table_args__ = (
        CheckConstraint(_DECISION_CHECK, name="valid_decision"),
        CheckConstraint(_HEALTH_SCORE_RANGE_CHECK, name="valid_health_score_at_decision"),
        CheckConstraint(_RISK_SCORE_RANGE_CHECK, name="valid_risk_score_at_decision"),
        Index("ix_release_decisions_release_assessment_id", "release_assessment_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    release_assessment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("release_assessments.id", ondelete="CASCADE"),
        nullable=False,
    )
    health_score_at_decision: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 2), nullable=True
    )
    risk_score_at_decision: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 2), nullable=True
    )
    decision: Mapped[str] = mapped_column(String(50), nullable=False)
    decided_by_role: Mapped[str] = mapped_column(String(50), nullable=False)
    decided_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    rationale: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    was_escalated: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    # NO updated_at — immutability enforced by omitting this column entirely.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    release_assessment: Mapped[ReleaseAssessment] = relationship(
        "ReleaseAssessment", back_populates="decision"
    )
