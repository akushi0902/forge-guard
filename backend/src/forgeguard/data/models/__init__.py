"""SQLAlchemy ORM model definitions.

The :class:`Base` declarative base is the single source of truth for table
metadata and naming conventions. Import it (and individual models) from here
rather than from the model submodules so callers have a stable import path.

Usage::

    from forgeguard.data.models import Base, User, RefreshToken
"""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Must match alembic/env.py NAMING_CONVENTION so auto-generated and hand-written
# constraint names are consistent across environments.
_NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Shared declarative base for all ForgeGuard ORM models."""

    metadata = MetaData(naming_convention=_NAMING_CONVENTION)


# Import models so their classes are registered on Base.metadata when this
# package is imported. The noqa comments suppress "imported but unused" linting.
from forgeguard.data.models.identity import (  # noqa: E402, F401
    Permission,
    RefreshToken,
    Role,
    RolePermission,
    User,
)
from forgeguard.data.models.governance import (  # noqa: E402, F401
    Policy,
    PolicyRule,
    Service,
)
from forgeguard.data.models.audit import (  # noqa: E402, F401
    AIConversation,
    AuditLog,
)
from forgeguard.data.models.prompt_template import PromptTemplate  # noqa: E402, F401
from forgeguard.data.models.assessments import (  # noqa: E402, F401
    Assessment,
    AssessmentScore,
    Finding,
    ReleaseAssessment,
    ReleaseDecision,
)

__all__ = [
    "AIConversation",
    "Assessment",
    "AssessmentScore",
    "AuditLog",
    "Base",
    "Finding",
    "Permission",
    "Policy",
    "PolicyRule",
    "PromptTemplate",
    "RefreshToken",
    "ReleaseAssessment",
    "ReleaseDecision",
    "Role",
    "RolePermission",
    "Service",
    "User",
]
