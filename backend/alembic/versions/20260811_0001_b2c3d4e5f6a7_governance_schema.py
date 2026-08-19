"""Governance domain schema: services, policies, policy_rules.

Creates three tables for the Governance domain:
    services     — registered applications under governance evaluation
    policies     — engineering policies grouped by dimension
    policy_rules — individual evaluation criteria with JSONB threshold configs

Also creates:
    GIN index on policy_rules(threshold_config)        — efficient JSONB queries
    Composite index on policy_rules(policy_id, is_active) — active rule lookups

Revision ID: b2c3d4e5f6a7
Revises:     a1b2c3d4e5f6 (identity_access_schema)
Create Date: 2026-08-11 00:01:00 UTC
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# ---------------------------------------------------------------------------
# Revision identifiers
# ---------------------------------------------------------------------------
revision: str = "b2c3d4e5f6a7"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # ── services ────────────────────────────────────────────────────────── #
    op.create_table(
        "services",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("repository_url", sa.String(2048), nullable=True),
        sa.Column("owner_team", sa.String(255), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "forge_catalog_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "is_demo",
            sa.Boolean,
            server_default="false",
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name="pk_services"),
        sa.UniqueConstraint("name", name="uq_services_name"),
    )
    op.create_index("ix_services_deleted_at", "services", ["deleted_at"])

    # ── policies ─────────────────────────────────────────────────────────── #
    op.create_table(
        "policies",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "service_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("dimension", sa.String(50), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean,
            server_default="true",
            nullable=False,
        ),
        sa.Column(
            "version",
            sa.Integer,
            server_default="1",
            nullable=False,
        ),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
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
            "dimension IN ('code_quality','test_coverage','security',"
            "'documentation','operations_readiness')",
            name="valid_dimension",
        ),
        sa.ForeignKeyConstraint(
            ["service_id"],
            ["services.id"],
            name="fk_policies_service_id_services",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_policies_created_by_users",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_policies"),
    )
    op.create_index("ix_policies_dimension", "policies", ["dimension"])
    op.create_index("ix_policies_deleted_at", "policies", ["deleted_at"])

    # ── policy_rules ─────────────────────────────────────────────────────── #
    op.create_table(
        "policy_rules",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "policy_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("rule_type", sa.String(100), nullable=False),
        sa.Column(
            "threshold_config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column(
            "weight",
            sa.Numeric(5, 2),
            server_default="1.0",
            nullable=False,
        ),
        sa.Column(
            "is_active",
            sa.Boolean,
            server_default="true",
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
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
            name="valid_severity",
        ),
        sa.ForeignKeyConstraint(
            ["policy_id"],
            ["policies.id"],
            name="fk_policy_rules_policy_id_policies",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_policy_rules"),
    )
    # GIN index for efficient JSONB containment queries.
    op.create_index(
        "ix_policy_rules_threshold_config_gin",
        "policy_rules",
        ["threshold_config"],
        postgresql_using="gin",
    )
    # Composite index: most common query — active rules for a given policy.
    op.create_index(
        "ix_policy_rules_policy_id_is_active",
        "policy_rules",
        ["policy_id", "is_active"],
    )


def downgrade() -> None:
    op.drop_index("ix_policy_rules_policy_id_is_active", table_name="policy_rules")
    op.drop_index(
        "ix_policy_rules_threshold_config_gin",
        table_name="policy_rules",
        postgresql_using="gin",
    )
    op.drop_table("policy_rules")
    op.drop_index("ix_policies_deleted_at", table_name="policies")
    op.drop_index("ix_policies_dimension", table_name="policies")
    op.drop_table("policies")
    op.drop_index("ix_services_deleted_at", table_name="services")
    op.drop_table("services")
