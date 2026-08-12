"""PolicyRepository: async CRUD for policies and policy_rules tables."""

from __future__ import annotations

import json
import uuid
from typing import Any

import asyncpg
import structlog

from forgeguard.data.repositories.base import BaseRepository

logger = structlog.get_logger(__name__)

_ALLOWED_INSERT: frozenset[str] = frozenset({
    "id", "service_id", "name", "dimension", "description",
    "is_active", "version", "created_by",
})

_ALLOWED_UPDATE: frozenset[str] = frozenset({
    "name", "description", "is_active", "service_id",
})

_ALLOWED_RULE_INSERT: frozenset[str] = frozenset({
    "id", "policy_id", "name", "rule_type", "threshold_config",
    "severity", "weight", "is_active",
})

_ALLOWED_RULE_UPDATE: frozenset[str] = frozenset({
    "name", "rule_type", "threshold_config", "severity", "weight", "is_active",
})


class PolicyRepository(BaseRepository):
    _table = "policies"

    async def get_by_id(
        self, id: str | uuid.UUID, *, include_deleted: bool = False
    ) -> dict[str, Any] | None:
        q = "SELECT * FROM policies WHERE id = $1"
        if not include_deleted:
            q += " AND deleted_at IS NULL"
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(q, uuid.UUID(str(id)))
        return self._row(row)

    async def list(
        self,
        *,
        filters: dict[str, Any] | None = None,
        cursor: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        params: list[Any] = []
        idx = 1
        q = "SELECT * FROM policies WHERE deleted_at IS NULL"
        if cursor:
            q += f" AND id > ${idx}"
            params.append(uuid.UUID(cursor))
            idx += 1
        q += f" ORDER BY id LIMIT ${idx}"
        params.append(limit)
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(q, *params)
        return self._rows(rows)

    async def create(self, data: dict[str, Any]) -> dict[str, Any]:
        query, values = self._safe_insert("policies", _ALLOWED_INSERT, data)
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, *values)
        return dict(row)  # type: ignore[arg-type]

    async def update(
        self, id: str | uuid.UUID, data: dict[str, Any]
    ) -> dict[str, Any] | None:
        set_clause, values = self._safe_update_clause(_ALLOWED_UPDATE, data)
        if not set_clause:
            return await self.get_by_id(id)
        values.append(uuid.UUID(str(id)))
        q = (
            f"UPDATE policies SET {set_clause}, updated_at = NOW() "
            f"WHERE id = ${len(values)} AND deleted_at IS NULL RETURNING *"
        )
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(q, *values)
        return self._row(row)

    async def soft_delete(self, id: str | uuid.UUID) -> bool:
        q = (
            "UPDATE policies SET deleted_at = NOW() "
            "WHERE id = $1 AND deleted_at IS NULL"
        )
        async with self._pool.acquire() as conn:
            result = await conn.execute(q, uuid.UUID(str(id)))
        return result == "UPDATE 1"

    async def find_active_by_dimension(self, dimension: str) -> list[dict[str, Any]]:
        q = (
            "SELECT * FROM policies WHERE dimension = $1 "
            "AND is_active = TRUE AND deleted_at IS NULL ORDER BY id"
        )
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(q, dimension)
        return self._rows(rows)

    async def get_with_rules(
        self, policy_id: str | uuid.UUID
    ) -> dict[str, Any] | None:
        policy = await self.get_by_id(policy_id)
        if policy is None:
            return None
        q = (
            "SELECT * FROM policy_rules WHERE policy_id = $1 "
            "AND deleted_at IS NULL ORDER BY id"
        )
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(q, uuid.UUID(str(policy_id)))
        policy["rules"] = self._rows(rows)
        return policy

    async def increment_version(
        self, policy_id: str | uuid.UUID
    ) -> dict[str, Any] | None:
        q = (
            "UPDATE policies SET version = version + 1, updated_at = NOW() "
            "WHERE id = $1 AND deleted_at IS NULL RETURNING *"
        )
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(q, uuid.UUID(str(policy_id)))
        return self._row(row)

    async def list_with_rule_counts(
        self,
        *,
        cursor: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Return policies with an attached rule_count; supports cursor pagination."""
        params: list[Any] = []
        idx = 1
        q = (
            "SELECT p.*, "
            "(SELECT COUNT(*) FROM policy_rules r WHERE r.policy_id = p.id) AS rule_count "
            "FROM policies p WHERE p.deleted_at IS NULL"
        )
        if cursor:
            q += f" AND p.created_at <= ${idx} AND p.id < ${idx + 1}"
            # cursor is "created_at_iso|id"
            try:
                ts_str, id_str = cursor.rsplit("|", 1)
                from datetime import datetime, timezone  # noqa: PLC0415
                ts = datetime.fromisoformat(ts_str)
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                params.extend([ts, uuid.UUID(id_str)])
                idx += 2
            except Exception:
                pass  # invalid cursor — ignore, return from beginning
        q += f" ORDER BY p.created_at DESC, p.id DESC LIMIT ${idx}"
        params.append(limit)
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(q, *params)
        return self._rows(rows)

    async def count_policies(self) -> int:
        q = "SELECT COUNT(*) FROM policies WHERE deleted_at IS NULL"
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(q)
        return row[0] if row else 0

    # ------------------------------------------------------------------
    # Policy rule methods
    # ------------------------------------------------------------------

    async def list_rules_by_policy(
        self, policy_id: str | uuid.UUID
    ) -> list[dict[str, Any]]:
        q = (
            "SELECT * FROM policy_rules WHERE policy_id = $1 ORDER BY created_at ASC"
        )
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(q, uuid.UUID(str(policy_id)))
        return self._rows(rows)

    async def get_rule_by_id(
        self, rule_id: str | uuid.UUID
    ) -> dict[str, Any] | None:
        q = "SELECT * FROM policy_rules WHERE id = $1"
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(q, uuid.UUID(str(rule_id)))
        return self._row(row)

    async def create_rule(self, data: dict[str, Any]) -> dict[str, Any]:
        # JSONB columns must be serialized as JSON strings for asyncpg.
        serialized = dict(data)
        if "threshold_config" in serialized and isinstance(
            serialized["threshold_config"], dict
        ):
            serialized["threshold_config"] = json.dumps(serialized["threshold_config"])
        query, values = self._safe_insert("policy_rules", _ALLOWED_RULE_INSERT, serialized)
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, *values)
        return dict(row)  # type: ignore[arg-type]

    async def update_rule(
        self, rule_id: str | uuid.UUID, data: dict[str, Any]
    ) -> dict[str, Any] | None:
        serialized = dict(data)
        if "threshold_config" in serialized and isinstance(
            serialized["threshold_config"], dict
        ):
            serialized["threshold_config"] = json.dumps(serialized["threshold_config"])
        set_clause, values = self._safe_update_clause(_ALLOWED_RULE_UPDATE, serialized)
        if not set_clause:
            return await self.get_rule_by_id(rule_id)
        values.append(uuid.UUID(str(rule_id)))
        q = (
            f"UPDATE policy_rules SET {set_clause}, updated_at = NOW() "
            f"WHERE id = ${len(values)} RETURNING *"
        )
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(q, *values)
        return self._row(row)

    async def toggle_rule(
        self, rule_id: str | uuid.UUID
    ) -> dict[str, Any] | None:
        q = (
            "UPDATE policy_rules SET is_active = NOT is_active, updated_at = NOW() "
            "WHERE id = $1 RETURNING *"
        )
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(q, uuid.UUID(str(rule_id)))
        return self._row(row)
