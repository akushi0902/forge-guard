"""Identity and Access domain SQLAlchemy ORM models.

Tables defined here form the data foundation for JWT-based authentication,
RBAC enforcement, and server-side refresh token management.

Models:
    User           — authenticated principals; supports soft-delete and lockout
    RefreshToken   — server-side token rotation chain (stores SHA-256 hash only)
    Role           — named RBAC role (one of six ForgeGuard personas)
    Permission     — named capability (e.g. 'release.approve')
    RolePermission — many-to-many join between Role and Permission

Design constraints:
    - No PostgreSQL ENUM types; use VARCHAR + CHECK constraints for portability.
    - PII columns (email, name_encrypted) must be encrypted at the application
      layer before writing; the database stores ciphertext only.
    - Passwords are never stored; only a bcrypt cost-12 hash is persisted.
    - Refresh tokens are never stored; only the SHA-256 hash is persisted.
    - All timestamps are timezone-aware (TIMESTAMPTZ).
    - Soft-delete via deleted_at IS NULL; callers must add this filter.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from forgeguard.data.models import Base

# ---------------------------------------------------------------------------
# Valid role values — kept in sync with the CHECK constraint below.
# ---------------------------------------------------------------------------
VALID_ROLES: tuple[str, ...] = (
    "developer",
    "tech_lead",
    "security_reviewer",
    "platform_admin",
    "engineering_manager",
    "operator",
)

_ROLE_CHECK_EXPR = (
    "role IN ("
    "'developer','tech_lead','security_reviewer',"
    "'platform_admin','engineering_manager','operator'"
    ")"
)


class User(Base):
    """Authenticated principal.

    Column notes:
        name_encrypted  — AES-256-GCM ciphertext; decrypt in the repository layer.
        password_hash   — 60-char bcrypt output; never store raw passwords.
        role            — VARCHAR with CHECK constraint (see VALID_ROLES).
        deleted_at      — NULL means active; non-NULL means soft-deleted.
        locked_until    — NULL or a past timestamp means the account is unlocked.
    """

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(_ROLE_CHECK_EXPR, name="valid_role"),
        Index("ix_users_email", "email"),
        Index("ix_users_deleted_at", "deleted_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    email: Mapped[str] = mapped_column(String(254), nullable=False, unique=True)
    name_encrypted: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    password_hash: Mapped[str] = mapped_column(String(60), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    failed_login_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    locked_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
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

    refresh_tokens: Mapped[list[RefreshToken]] = relationship(
        "RefreshToken",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class RefreshToken(Base):
    """Server-side refresh token record.

    Column notes:
        token_hash  — SHA-256 hex digest of the actual token; raw token is
                      never persisted to the database.
        revoked_at  — NULL means the token is still valid (subject to expiry).

    The composite index on (user_id, revoked_at) supports efficient queries
    that filter active tokens for a given user.
    """

    __tablename__ = "refresh_tokens"
    __table_args__ = (
        Index("ix_refresh_tokens_user_id_revoked_at", "user_id", "revoked_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    replaced_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("refresh_tokens.id", ondelete="SET NULL"),
        nullable=True,
    )

    user: Mapped[User] = relationship("User", back_populates="refresh_tokens")


class Role(Base):
    """Named RBAC role corresponding to a ForgeGuard persona."""

    __tablename__ = "roles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    name: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    permissions: Mapped[list[Permission]] = relationship(
        "Permission",
        secondary="role_permissions",
        back_populates="roles",
        viewonly=True,
    )


class Permission(Base):
    """Named capability that can be granted to a Role."""

    __tablename__ = "permissions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    roles: Mapped[list[Role]] = relationship(
        "Role",
        secondary="role_permissions",
        back_populates="permissions",
        viewonly=True,
    )


class RolePermission(Base):
    """Join table granting a Permission to a Role.

    Composite primary key (role_id, permission_id) prevents duplicate grants.
    """

    __tablename__ = "role_permissions"

    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    permission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True,
    )
