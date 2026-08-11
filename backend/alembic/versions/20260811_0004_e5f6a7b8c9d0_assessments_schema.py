"""Assessments domain schema: assessments, scores, findings, release data.

Creates 5 tables for the Assessments domain:
    assessments          — governance evaluation runs (health check or release risk)
    assessment_scores    — computed overall + dimension breakdown scores
    findings             — policy violations detected during evaluations
    release_assessments  — release readiness checks for a commit SHA / PR
    release_decisions    — immutable approve/block records (no UPDATE privilege)

Also creates composite indexes optimised for primary access patterns:
    assessments(service_id, created_at)
    assessment_scores(service_id, score_type, created_at)
    findings(service_id, severity, status)        — dashboard query
    findings(assessment_id, severity)             — assessment detail view
    release_assessments(service_id, created_at)
    release_decisions(release_assessment_id)

Revision ID: e5f6a7b8c9d0
Revises:     d4e5f6a7b8c9 (prompt_templates)
Create Date: 2026-08-11 00:04:00 UTC
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# ---------------------------------------------------------------------------
# Revision identifiers
# ---------------------------------------------------------------------------
revision: str = "e5f6a7b8c9d0"
down_revision: str | None = "d4e5f6a7b8c9"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # ------------------------------------------------------------------ #
    # assessments
    # ------------------------------------------------------------------ #
    op.create_table(
        "assessments",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("service_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assessment_type", sa.String(50), nullable=False),
        sa.Column("trigger_type", sa.String(50), nullable=False),
        sa.Column("triggered_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("collected_data", postgresql.JSONB(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "assessment_type IN ('health_check','release_risk')",
            name="ck_assessments_valid_assessment_type",
        ),
        sa.CheckConstraint(
            "trigger_type IN ('manual','scheduled','webhook')",
            name="ck_assessments_valid_trigger_type",
        ),
        sa.CheckConstraint(
            "status IN ('pending','in_progress','completed','failed')",
            name="ck_assessments_valid_assessment_status",
        ),
        sa.ForeignKeyConstraint(
            ["service_id"],
            ["services.id"],
            name="fk_assessments_service_id_services",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["triggered_by"],
            ["users.id"],
            name="fk_assessments_triggered_by_users",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_assessments"),
    )
    op.create_index(
        "ix_assessments_service_id_created_at",
        "assessments",
        ["service_id", "created_at"],
    )
    op.create_index("ix_assessments_status", "assessments", ["status"])

    # ------------------------------------------------------------------ #
    # assessment_scores
    # ------------------------------------------------------------------ #
    op.create_table(
        "assessment_scores",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("assessment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("service_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("score_type", sa.String(50), nullable=False),
        sa.Column("overall_score", sa.Numeric(5, 2), nullable=False),
        sa.Column("dimension_scores", postgresql.JSONB(), nullable=False),
        sa.Column("contributing_factors", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "overall_score >= 0 AND overall_score <= 100",
            name="ck_assessment_scores_valid_score_range",
        ),
        sa.ForeignKeyConstraint(
            ["assessment_id"],
            ["assessments.id"],
            name="fk_assessment_scores_assessment_id_assessments",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["service_id"],
            ["services.id"],
            name="fk_assessment_scores_service_id_services",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_assessment_scores"),
    )
    op.create_index(
        "ix_assessment_scores_service_id_score_type_created_at",
        "assessment_scores",
        ["service_id", "score_type", "created_at"],
    )

    # ------------------------------------------------------------------ #
    # findings
    # ------------------------------------------------------------------ #
    op.create_table(
        "findings",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("assessment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("service_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("policy_rule_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("dimension", sa.String(50), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="open"),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("evidence", postgresql.JSONB(), nullable=True),
        sa.Column("ai_explanation", postgresql.JSONB(), nullable=True),
        sa.Column("confidence_score", sa.Numeric(3, 2), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "severity IN ('critical','high','medium','low')",
            name="ck_findings_valid_severity",
        ),
        sa.CheckConstraint(
            "dimension IN ('code_quality','test_coverage','security',"
            "'documentation','operations_readiness')",
            name="ck_findings_valid_dimension",
        ),
        sa.CheckConstraint(
            "status IN ('open','in_progress','resolved','suppressed')",
            name="ck_findings_valid_finding_status",
        ),
        sa.CheckConstraint(
            "confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)",
            name="ck_findings_valid_confidence_score",
        ),
        sa.ForeignKeyConstraint(
            ["assessment_id"],
            ["assessments.id"],
            name="fk_findings_assessment_id_assessments",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["service_id"],
            ["services.id"],
            name="fk_findings_service_id_services",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["policy_rule_id"],
            ["policy_rules.id"],
            name="fk_findings_policy_rule_id_policy_rules",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_findings"),
    )
    op.create_index(
        "ix_findings_service_id_severity_status",
        "findings",
        ["service_id", "severity", "status"],
    )
    op.create_index(
        "ix_findings_assessment_id_severity",
        "findings",
        ["assessment_id", "severity"],
    )

    # ------------------------------------------------------------------ #
    # release_assessments
    # ------------------------------------------------------------------ #
    op.create_table(
        "release_assessments",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("service_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("commit_sha", sa.String(255), nullable=True),
        sa.Column("pr_reference", sa.String(2048), nullable=True),
        sa.Column("requested_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("change_analysis", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending','in_progress','completed','failed')",
            name="ck_release_assessments_valid_release_assessment_status",
        ),
        sa.ForeignKeyConstraint(
            ["service_id"],
            ["services.id"],
            name="fk_release_assessments_service_id_services",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by"],
            ["users.id"],
            name="fk_release_assessments_requested_by_users",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_release_assessments"),
    )
    op.create_index(
        "ix_release_assessments_service_id_created_at",
        "release_assessments",
        ["service_id", "created_at"],
    )
    op.create_index(
        "ix_release_assessments_status", "release_assessments", ["status"]
    )

    # ------------------------------------------------------------------ #
    # release_decisions  — APPEND-ONLY (no updated_at, no UPDATE privilege)
    # ------------------------------------------------------------------ #
    op.create_table(
        "release_decisions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "release_assessment_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("health_score_at_decision", sa.Numeric(5, 2), nullable=True),
        sa.Column("risk_score_at_decision", sa.Numeric(5, 2), nullable=True),
        sa.Column("decision", sa.String(50), nullable=False),
        sa.Column("decided_by_role", sa.String(50), nullable=False),
        sa.Column("decided_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "was_escalated",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        # NO updated_at column — immutability enforced at schema level.
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "decision IN ('APPROVE','CONDITIONAL_APPROVE','BLOCK')",
            name="ck_release_decisions_valid_decision",
        ),
        sa.CheckConstraint(
            "health_score_at_decision >= 0 AND health_score_at_decision <= 100",
            name="ck_release_decisions_valid_health_score_at_decision",
        ),
        sa.CheckConstraint(
            "risk_score_at_decision >= 0 AND risk_score_at_decision <= 100",
            name="ck_release_decisions_valid_risk_score_at_decision",
        ),
        sa.ForeignKeyConstraint(
            ["release_assessment_id"],
            ["release_assessments.id"],
            name="fk_release_decisions_release_assessment_id_release_assessments",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["decided_by"],
            ["users.id"],
            name="fk_release_decisions_decided_by_users",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_release_decisions"),
    )
    op.create_index(
        "ix_release_decisions_release_assessment_id",
        "release_decisions",
        ["release_assessment_id"],
    )

    # Revoke UPDATE on release_decisions for the application role (immutability).
    # This is best-effort: the role may not exist in all environments (e.g. tests).
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'forgeguard_app') THEN
                REVOKE UPDATE ON release_decisions FROM forgeguard_app;
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    # Restore UPDATE privilege before dropping (allows clean re-migration).
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'forgeguard_app') THEN
                GRANT UPDATE ON release_decisions TO forgeguard_app;
            END IF;
        END $$;
        """
    )

    op.drop_table("release_decisions")
    op.drop_table("release_assessments")
    op.drop_table("findings")
    op.drop_table("assessment_scores")
    op.drop_table("assessments")
