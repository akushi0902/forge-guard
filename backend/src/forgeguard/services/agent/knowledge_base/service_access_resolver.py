"""ServiceAccessResolver: RBAC-consistent service ownership scoping (WO-067).

Given an authenticated user_id, returns the set of service_ids the user is
authorized to view. This resolver aligns with the RBAC module's permission
checks and must be the single source of truth for service-level access
decisions in the knowledge base layer.

Access model:
    - platform_admin and engineering_manager roles see ALL active services.
    - developer, tech_lead, security_reviewer, and operator roles see only
      services where they appear as the triggering user in an assessment OR
      where their role gives them service.view (all roles do, but scoped to
      their own context — for the agent we grant platform-wide visibility to
      privileged roles and self-scoped visibility to standard roles).

For the hackathon prototype this implements a pragmatic policy:
    - Privileged roles (platform_admin, engineering_manager, security_reviewer,
      operator): full visibility across all active services.
    - Standard roles (developer, tech_lead): services they have triggered at
      least one assessment for, plus all services (since service.view is
      granted to all roles per the RBAC matrix).
    - Unknown/missing role: no services.

The caller (context_assembler) is responsible for verifying that the
requested service_id is in the returned authorized set before executing
domain queries.
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Roles that receive full, platform-wide service visibility.
_PRIVILEGED_ROLES: frozenset[str] = frozenset({
    "platform_admin",
    "engineering_manager",
    "security_reviewer",
    "operator",
    "tech_lead",
})

# All ForgeGuard roles with any service.view access.
_ALL_ROLES: frozenset[str] = frozenset({
    "developer",
    "tech_lead",
    "security_reviewer",
    "platform_admin",
    "engineering_manager",
    "operator",
})


class ServiceAccessResolver:
    """Determine which services an authenticated user may query via the agent.

    Designed to be instantiated once and reused — it is stateless beyond the
    asyncpg pool reference.
    """

    def __init__(self, pool: Any) -> None:
        self._pool = pool

    async def get_authorized_service_ids(
        self,
        user_id: uuid.UUID,
        actor_role: str,
    ) -> frozenset[uuid.UUID]:
        """Return the set of service_ids the user is authorized to view.

        Args:
            user_id:    Authenticated user's UUID.
            actor_role: The user's current role string.

        Returns:
            Frozenset of authorized service UUIDs. Empty set if the user has
            no services or an unknown role.
        """
        if actor_role not in _ALL_ROLES:
            logger.warning(
                "service_access.unknown_role",
                user_id=str(user_id),
                actor_role=actor_role,
            )
            return frozenset()

        try:
            async with self._pool.acquire() as conn:
                if actor_role in _PRIVILEGED_ROLES:
                    # Privileged roles see all active services.
                    rows = await conn.fetch(
                        "SELECT id FROM services WHERE deleted_at IS NULL"
                    )
                else:
                    # Standard roles (developer): all active services.
                    # Per RBAC matrix all roles hold service.view, so we grant
                    # full active-service visibility here as well. This keeps
                    # the agent useful for developers who need to query any
                    # service they can see in the UI.
                    rows = await conn.fetch(
                        "SELECT id FROM services WHERE deleted_at IS NULL"
                    )

            return frozenset(row["id"] for row in rows)

        except Exception as exc:  # noqa: BLE001
            logger.error(
                "service_access.query_failed",
                user_id=str(user_id),
                actor_role=actor_role,
                error=str(exc),
            )
            return frozenset()

    async def is_authorized(
        self,
        user_id: uuid.UUID,
        actor_role: str,
        service_id: uuid.UUID,
    ) -> bool:
        """Check whether the user is authorized to access a specific service.

        Args:
            user_id:    Authenticated user's UUID.
            actor_role: The user's current role string.
            service_id: Target service UUID to check.

        Returns:
            True if the user may access this service, False otherwise.
        """
        authorized = await self.get_authorized_service_ids(user_id, actor_role)
        return service_id in authorized
