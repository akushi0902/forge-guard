"""Identity and Access domain schema tables.

Creates the five tables that form the ForgeGuard Identity and Access domain:
    users           — authenticated principals with RBAC role, lockout, soft-delete
    refresh_tokens  — server-side token rotation chain (SHA-256 hashes only)
    roles           — named RBAC personas (pre-populated with 6 ForgeGuard roles)
    permissions     — named capabilities (pre-populated with 10 permissions)
    role_permissions — RBAC permission matrix (pre-populated)

Revision ID: a1b2c3d4e5f6
Revises:     (none — first migration)
Create Date: 2026-08-11 00:00:00 UTC
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# ---------------------------------------------------------------------------
# Revision identifiers
# ---------------------------------------------------------------------------
revision: str = "a1b2c3d4e5f6"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


# ---------------------------------------------------------------------------
# Seed data
# ---------------------------------------------------------------------------

_ROLES = [
    ("developer", "Software engineer building and maintaining services"),
    ("tech_lead", "Senior engineer responsible for technical decisions and reviews"),
    ("security_reviewer", "Security specialist who reviews and enforces policies"),
    ("platform_admin", "Platform administrator with full system access"),
    ("engineering_manager", "Engineering manager overseeing release and team health"),
    ("operator", "Operations staff monitoring runtime health"),
]

_PERMISSIONS = [
    ("service.view", "View registered services and their metadata"),
    ("assessment.request", "Request a new compliance or risk assessment"),
    ("release.approve", "Approve a proposed software release"),
    ("release.block", "Block a proposed software release"),
    ("exception.request", "Request an exception to a policy requirement"),
    ("exception.approve", "Approve or deny a policy exception request"),
    ("policy.manage", "Create, update, and delete governance policies"),
    ("rbac.manage", "Manage roles and permission assignments"),
    ("health.monitor", "View operational health dashboards and metrics"),
    ("trends.view", "View analytics and engineering trend data"),
]

# RBAC matrix: role_name → list of permission names granted
_RBAC_MATRIX: dict[str, list[str]] = {
    "developer": [
        "service.view",
        "assessment.request",
        "exception.request",
        "trends.view",
    ],
    "tech_lead": [
        "service.view",
        "assessment.request",
        "release.approve",
        "exception.request",
        "exception.approve",
        "trends.view",
    ],
    "security_reviewer": [
        "service.view",
        "assessment.request",
        "release.approve",
        "release.block",
        "exception.approve",
        "policy.manage",
        "health.monitor",
        "trends.view",
    ],
    "platform_admin": [
        "service.view",
        "assessment.request",
        "release.approve",
        "release.block",
        "exception.request",
        "exception.approve",
        "policy.manage",
        "rbac.manage",
        "health.monitor",
        "trends.view",
    ],
    "engineering_manager": [
        "service.view",
        "assessment.request",
        "release.approve",
        "health.monitor",
        "trends.view",
    ],
    "operator": [
        "service.view",
        "health.monitor",
    ],
}


def upgrade() -> None:
    # ------------------------------------------------------------------ #
    # users
    # ------------------------------------------------------------------ #
    op.create_table(
        "users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("name_encrypted", sa.LargeBinary, nullable=True),
        sa.Column("password_hash", sa.String(60), nullable=False),
        sa.Column("role", sa.String(50), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "failed_login_attempts",
            sa.Integer,
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.CheckConstraint(
            "role IN ("
            "'developer','tech_lead','security_reviewer',"
            "'platform_admin','engineering_manager','operator'"
            ")",
            name="valid_role",
        ),
    )
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_deleted_at", "users", ["deleted_at"])

    # ------------------------------------------------------------------ #
    # refresh_tokens
    # ------------------------------------------------------------------ #
    op.create_table(
        "refresh_tokens",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_refresh_tokens_user_id_revoked_at",
        "refresh_tokens",
        ["user_id", "revoked_at"],
    )

    # ------------------------------------------------------------------ #
    # roles
    # ------------------------------------------------------------------ #
    op.create_table(
        "roles",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(50), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("name", name="uq_roles_name"),
    )

    # ------------------------------------------------------------------ #
    # permissions
    # ------------------------------------------------------------------ #
    op.create_table(
        "permissions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("name", name="uq_permissions_name"),
    )

    # ------------------------------------------------------------------ #
    # role_permissions (association table)
    # ------------------------------------------------------------------ #
    op.create_table(
        "role_permissions",
        sa.Column(
            "role_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("roles.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "permission_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("permissions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )

    # ------------------------------------------------------------------ #
    # Seed roles, permissions, and RBAC matrix
    # ------------------------------------------------------------------ #
    bind = op.get_bind()

    # Insert roles and build name → id map
    role_ids: dict[str, str] = {}
    for role_name, role_desc in _ROLES:
        role_id = str(uuid.uuid4())
        role_ids[role_name] = role_id
        bind.execute(
            sa.text(
                "INSERT INTO roles (id, name, description) VALUES (:id, :name, :description)"
            ),
            {"id": role_id, "name": role_name, "description": role_desc},
        )

    # Insert permissions and build name → id map
    perm_ids: dict[str, str] = {}
    for perm_name, perm_desc in _PERMISSIONS:
        perm_id = str(uuid.uuid4())
        perm_ids[perm_name] = perm_id
        bind.execute(
            sa.text(
                "INSERT INTO permissions (id, name, description) VALUES (:id, :name, :description)"
            ),
            {"id": perm_id, "name": perm_name, "description": perm_desc},
        )

    # Populate role_permissions matrix
    for role_name, perm_names in _RBAC_MATRIX.items():
        rid = role_ids[role_name]
        for perm_name in perm_names:
            pid = perm_ids[perm_name]
            bind.execute(
                sa.text(
                    "INSERT INTO role_permissions (role_id, permission_id) VALUES (:rid, :pid)"
                ),
                {"rid": rid, "pid": pid},
            )


def downgrade() -> None:
    op.drop_table("role_permissions")
    op.drop_table("permissions")
    op.drop_table("roles")
    op.drop_index("ix_refresh_tokens_user_id_revoked_at", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
    op.drop_index("ix_users_deleted_at", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
