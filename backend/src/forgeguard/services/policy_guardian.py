"""PolicyGuardianService: orchestrates policy and rule CRUD with audit logging (WO-035)."""

from __future__ import annotations

import uuid
from typing import Any, Optional

import structlog

from forgeguard.data.repositories.policies import PolicyRepository
from forgeguard.services.audit import AuditService

logger = structlog.get_logger(__name__)


class PolicyGuardianService:
    """Coordinates policy/rule persistence, version management, and audit logging."""

    def __init__(
        self,
        repo: PolicyRepository,
        audit_service: Optional[AuditService] = None,
    ) -> None:
        self._repo = repo
        self._audit = audit_service

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _audit_log(self, **kwargs: Any) -> None:
        if self._audit is None:
            return
        try:
            await self._audit.log_event(**kwargs)
        except Exception:
            logger.warning("policy_guardian.audit_log_failed", kwargs=str(kwargs))

    @staticmethod
    def _row_to_serializable(row: dict[str, Any] | None) -> dict[str, Any] | None:
        if row is None:
            return None
        result = {}
        for k, v in row.items():
            if isinstance(v, uuid.UUID):
                result[k] = str(v)
            elif hasattr(v, "isoformat"):
                result[k] = v.isoformat()
            else:
                result[k] = v
        return result

    # ------------------------------------------------------------------
    # Policy operations
    # ------------------------------------------------------------------

    async def list_policies(
        self,
        *,
        cursor: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Return cursor-paginated policy list with rule counts and total_count."""
        rows = await self._repo.list_with_rule_counts(cursor=cursor, limit=limit + 1)
        total_count = await self._repo.count_policies()

        has_more = len(rows) > limit
        page = rows[:limit]

        next_cursor: str | None = None
        if has_more and page:
            last = page[-1]
            ca = last["created_at"]
            ts_str = ca.isoformat() if hasattr(ca, "isoformat") else str(ca)
            next_cursor = f"{ts_str}|{last['id']}"

            import base64  # noqa: PLC0415
            next_cursor = base64.b64encode(next_cursor.encode()).decode()

        return {
            "items": page,
            "next_cursor": next_cursor,
            "total_count": total_count,
        }

    async def get_policy(self, policy_id: str | uuid.UUID) -> dict[str, Any] | None:
        return await self._repo.get_by_id(policy_id)

    async def create_policy(
        self,
        data: dict[str, Any],
        *,
        actor_id: str | None,
        actor_role: str,
    ) -> dict[str, Any]:
        new_id = uuid.uuid4()
        payload = {
            "id": new_id,
            "name": data["name"],
            "dimension": data["dimension"],
            "description": data.get("description"),
            "is_active": data.get("is_active", True),
            "version": 1,
            "created_by": uuid.UUID(str(actor_id)) if actor_id else None,
        }
        created = await self._repo.create(payload)
        await self._audit_log(
            actor_id=actor_id,
            actor_role=actor_role,
            action="policy.created",
            resource_type="policy",
            resource_id=new_id,
            after_state=self._row_to_serializable(created),
        )
        return created

    async def update_policy(
        self,
        policy_id: str | uuid.UUID,
        data: dict[str, Any],
        *,
        actor_id: str | None,
        actor_role: str,
        expected_version: int | None = None,
    ) -> dict[str, Any] | None:
        before = await self._repo.get_by_id(policy_id)
        if before is None:
            return None

        if expected_version is not None and before.get("version") != expected_version:
            raise ValueError(
                f"Version mismatch: expected {expected_version}, "
                f"found {before.get('version')}"
            )

        update_payload = {
            k: v
            for k, v in data.items()
            if k in {"name", "description", "is_active"} and v is not None
        }
        updated = await self._repo.update(policy_id, update_payload)
        if updated:
            updated = await self._repo.increment_version(policy_id)
        await self._audit_log(
            actor_id=actor_id,
            actor_role=actor_role,
            action="policy.updated",
            resource_type="policy",
            resource_id=uuid.UUID(str(policy_id)),
            before_state=self._row_to_serializable(before),
            after_state=self._row_to_serializable(updated),
        )
        return updated

    # ------------------------------------------------------------------
    # Rule operations
    # ------------------------------------------------------------------

    async def create_rule(
        self,
        policy_id: str | uuid.UUID,
        data: dict[str, Any],
        *,
        actor_id: str | None,
        actor_role: str,
    ) -> dict[str, Any] | None:
        policy = await self._repo.get_by_id(policy_id)
        if policy is None:
            return None

        new_id = uuid.uuid4()
        payload = {
            "id": new_id,
            "policy_id": uuid.UUID(str(policy_id)),
            "name": data["name"],
            "rule_type": data["rule_type"],
            "threshold_config": data["threshold_config"],
            "severity": data["severity"],
            "weight": data["weight"],
            "is_active": data.get("is_active", True),
        }
        created = await self._repo.create_rule(payload)
        await self._audit_log(
            actor_id=actor_id,
            actor_role=actor_role,
            action="policy_rule.created",
            resource_type="policy_rule",
            resource_id=new_id,
            after_state=self._row_to_serializable(created),
        )
        return created

    async def update_rule(
        self,
        policy_id: str | uuid.UUID,
        rule_id: str | uuid.UUID,
        data: dict[str, Any],
        *,
        actor_id: str | None,
        actor_role: str,
    ) -> dict[str, Any] | None:
        before = await self._repo.get_rule_by_id(rule_id)
        if before is None:
            return None
        if str(before.get("policy_id")) != str(policy_id):
            return None

        update_payload = {
            k: v
            for k, v in data.items()
            if k in {"name", "rule_type", "threshold_config", "severity", "weight", "is_active"}
            and v is not None
        }
        updated = await self._repo.update_rule(rule_id, update_payload)
        await self._audit_log(
            actor_id=actor_id,
            actor_role=actor_role,
            action="policy_rule.updated",
            resource_type="policy_rule",
            resource_id=uuid.UUID(str(rule_id)),
            before_state=self._row_to_serializable(before),
            after_state=self._row_to_serializable(updated),
        )
        return updated

    async def toggle_rule(
        self,
        policy_id: str | uuid.UUID,
        rule_id: str | uuid.UUID,
        *,
        actor_id: str | None,
        actor_role: str,
    ) -> dict[str, Any] | None:
        before = await self._repo.get_rule_by_id(rule_id)
        if before is None:
            return None
        if str(before.get("policy_id")) != str(policy_id):
            return None

        updated = await self._repo.toggle_rule(rule_id)
        await self._audit_log(
            actor_id=actor_id,
            actor_role=actor_role,
            action="policy_rule.toggled",
            resource_type="policy_rule",
            resource_id=uuid.UUID(str(rule_id)),
            before_state=self._row_to_serializable(before),
            after_state=self._row_to_serializable(updated),
        )
        return updated
