"""UserRepository: async CRUD for the users table."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import asyncpg
import structlog

from forgeguard.data.repositories.base import BaseRepository

logger = structlog.get_logger(__name__)

_ALLOWED_INSERT: frozenset[str] = frozenset({
    "id", "email", "name_encrypted", "password_hash", "role",
    "is_active", "failed_login_attempts", "locked_until",
})

_ALLOWED_UPDATE: frozenset[str] = frozenset({
    "role", "is_active", "name_encrypted", "failed_login_attempts", "locked_until",
})


class UserRepository(BaseRepository):
    _table = "users"

    async def get_by_id(
        self, id: str | uuid.UUID, *, include_deleted: bool = False
    ) -> dict[str, Any] | None:
        q = "SELECT * FROM users WHERE id = $1"
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
        q = "SELECT * FROM users WHERE deleted_at IS NULL"
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
        query, values = self._safe_insert("users", _ALLOWED_INSERT, data)
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
            f"UPDATE users SET {set_clause}, updated_at = NOW() "
            f"WHERE id = ${len(values)} AND deleted_at IS NULL RETURNING *"
        )
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(q, *values)
        return self._row(row)

    async def soft_delete(self, id: str | uuid.UUID) -> bool:
        q = (
            "UPDATE users SET deleted_at = NOW() "
            "WHERE id = $1 AND deleted_at IS NULL"
        )
        async with self._pool.acquire() as conn:
            result = await conn.execute(q, uuid.UUID(str(id)))
        return result == "UPDATE 1"

    async def find_by_email(self, email: str) -> dict[str, Any] | None:
        q = "SELECT * FROM users WHERE email = $1 AND deleted_at IS NULL"
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(q, email)
        return self._row(row)

    async def update_failed_login_attempts(
        self, id: str | uuid.UUID, count: int
    ) -> None:
        q = (
            "UPDATE users SET failed_login_attempts = $1, updated_at = NOW() "
            "WHERE id = $2 AND deleted_at IS NULL"
        )
        async with self._pool.acquire() as conn:
            await conn.execute(q, count, uuid.UUID(str(id)))

    async def lock_account(
        self, id: str | uuid.UUID, locked_until: datetime
    ) -> None:
        q = (
            "UPDATE users SET locked_until = $1, updated_at = NOW() "
            "WHERE id = $2 AND deleted_at IS NULL"
        )
        async with self._pool.acquire() as conn:
            await conn.execute(q, locked_until, uuid.UUID(str(id)))

    async def check_permissions(self, user_id: str | uuid.UUID) -> list[str]:
        q = """
            SELECT p.name
            FROM permissions p
            JOIN role_permissions rp ON rp.permission_id = p.id
            JOIN roles r ON r.id = rp.role_id
            JOIN users u ON u.role = r.name
            WHERE u.id = $1 AND u.deleted_at IS NULL
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(q, uuid.UUID(str(user_id)))
        return [row["name"] for row in rows]
