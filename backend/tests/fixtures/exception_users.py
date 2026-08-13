"""Mock user fixtures for exception approval tests (WO-064).

Provides Security Reviewer and Platform Admin users with fixed UUIDs
for deterministic test assertions.  JWT-claims-style dicts are included
for tests that stub the authentication dependency.
"""

from __future__ import annotations

import uuid
from typing import Any

SECURITY_REVIEWER_ID = uuid.UUID("cc000000-0000-0000-0000-000000000001")
PLATFORM_ADMIN_ID = uuid.UUID("cc000000-0000-0000-0000-000000000002")
DEVELOPER_ID = uuid.UUID("cc000000-0000-0000-0000-000000000003")
TECH_LEAD_ID = uuid.UUID("cc000000-0000-0000-0000-000000000004")

# ---------------------------------------------------------------------------
# JWT-claims-style dicts (mirror the shape parsed by the auth dependency)
# ---------------------------------------------------------------------------

SECURITY_REVIEWER_CLAIMS: dict[str, Any] = {
    "sub": str(SECURITY_REVIEWER_ID),
    "role": "security_reviewer",
    "email": "security@example.com",
    "name": "Security Reviewer User",
}

PLATFORM_ADMIN_CLAIMS: dict[str, Any] = {
    "sub": str(PLATFORM_ADMIN_ID),
    "role": "platform_admin",
    "email": "admin@example.com",
    "name": "Platform Admin User",
}

DEVELOPER_CLAIMS: dict[str, Any] = {
    "sub": str(DEVELOPER_ID),
    "role": "developer",
    "email": "dev@example.com",
    "name": "Developer User",
}

TECH_LEAD_CLAIMS: dict[str, Any] = {
    "sub": str(TECH_LEAD_ID),
    "role": "tech_lead",
    "email": "tl@example.com",
    "name": "Tech Lead User",
}


def make_current_user(role: str, user_id: uuid.UUID | None = None) -> Any:
    """Build a CurrentUser-like object for dependency injection mocking."""
    from forgeguard.api.dependencies.auth import CurrentUser  # noqa: PLC0415

    uid = user_id or uuid.uuid4()
    return CurrentUser(user_id=uid, role=role)


SECURITY_REVIEWER_USER = make_current_user("security_reviewer", SECURITY_REVIEWER_ID)
PLATFORM_ADMIN_USER = make_current_user("platform_admin", PLATFORM_ADMIN_ID)
DEVELOPER_USER = make_current_user("developer", DEVELOPER_ID)
TECH_LEAD_USER = make_current_user("tech_lead", TECH_LEAD_ID)
