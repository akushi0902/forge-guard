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

    async def increment_failed_attempts(self, id: str | uuid.UUID) -> int:
        """Atomically increment the failed login counter.  Returns the new count."""
        q = (
            "UPDATE users SET failed_login_attempts = failed_login_attempts + 1, updated_at = NOW() "
            "WHERE id = $1 AND deleted_at IS NULL RETURNING failed_login_attempts"
        )
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(q, uuid.UUID(str(id)))
        return int(row["failed_login_attempts"]) if row else 0

    async def reset_failed_attempts(self, id: str | uuid.UUID) -> None:
        """Reset the failed login counter to 0 and clear any lockout."""
        q = (
            "UPDATE users SET failed_login_attempts = 0, locked_until = NULL, updated_at = NOW() "
            "WHERE id = $1 AND deleted_at IS NULL"
        )
        async with self._pool.acquire() as conn:
            await conn.execute(q, uuid.UUID(str(id)))

    async def update_password(self, id: str | uuid.UUID, password_hash: str) -> None:
        """Update a user's password hash.  Security-sensitive — dedicated method."""
        q = (
            "UPDATE users SET password_hash = $1, updated_at = NOW() "
            "WHERE id = $2 AND deleted_at IS NULL"
        )
        async with self._pool.acquire() as conn:
            await conn.execute(q, password_hash, uuid.UUID(str(id)))

    async def list_all(
        self,
        *,
        cursor: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Return all non-deleted users with cursor-based pagination.

        Cursor is a base64-encoded ``created_at|id`` composite key.
        Results are ordered by (created_at DESC, id DESC).
        """
        import base64  # noqa: PLC0415

        params: list[Any] = []
        idx = 1
        q = "SELECT * FROM users WHERE deleted_at IS NULL"

        if cursor:
            try:
                decoded = base64.b64decode(cursor.encode()).decode()
                ts_str, id_str = decoded.split("|", 1)
                cursor_ts = datetime.fromisoformat(ts_str)
                cursor_id = uuid.UUID(id_str)
                q += (
                    f" AND (created_at < ${idx} "
                    f"OR (created_at = ${idx} AND id < ${idx + 1}))"
                )
                params.extend([cursor_ts, cursor_id])
                idx += 2
            except Exception:
                logger.warning("user_repository.list_all.invalid_cursor", cursor=cursor)

        q += f" ORDER BY created_at DESC, id DESC LIMIT ${idx}"
        params.append(limit)

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(q, *params)
        return self._rows(rows)

    async def count_all(self) -> int:
        """Return total count of non-deleted users."""
        q = "SELECT COUNT(*) FROM users WHERE deleted_at IS NULL"
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(q)
        return int(row["count"]) if row else 0

    async def count_by_role(self, role: str) -> int:
        """Return count of active, non-deleted users with the given role."""
        q = (
            "SELECT COUNT(*) FROM users "
            "WHERE role = $1 AND is_active = TRUE AND deleted_at IS NULL"
        )
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(q, role)
        return int(row["count"]) if row else 0

    async def update_role(
        self, user_id: str | uuid.UUID, new_role: str
    ) -> dict[str, Any] | None:
        """Update a user's role and return the updated row."""
        q = (
            "UPDATE users SET role = $1, updated_at = NOW() "
            "WHERE id = $2 AND deleted_at IS NULL RETURNING *"
        )
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(q, new_role, uuid.UUID(str(user_id)))
        return self._row(row)

    async def update_status(
        self, user_id: str | uuid.UUID, is_active: bool
    ) -> dict[str, Any] | None:
        """Update a user's active status and return the updated row."""
        q = (
            "UPDATE users SET is_active = $1, updated_at = NOW() "
            "WHERE id = $2 AND deleted_at IS NULL RETURNING *"
        )
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(q, is_active, uuid.UUID(str(user_id)))
        return self._row(row)

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
