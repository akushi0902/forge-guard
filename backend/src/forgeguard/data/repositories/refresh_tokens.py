"""RefreshTokenRepository: async CRUD for the refresh_tokens table."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import asyncpg
import structlog

from forgeguard.data.repositories.base import BaseRepository

logger = structlog.get_logger(__name__)

_ALLOWED_INSERT: frozenset[str] = frozenset({
    "id", "user_id", "token_hash", "expires_at",
})


class RefreshTokenRepository(BaseRepository):
    _table = "refresh_tokens"

    async def get_by_id(
        self, id: str | uuid.UUID, *, include_deleted: bool = False
    ) -> dict[str, Any] | None:
        q = "SELECT * FROM refresh_tokens WHERE id = $1"
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
        q = "SELECT * FROM refresh_tokens WHERE TRUE"
        if cursor:
            q += f" AND id > ${idx}"
            params.append(uuid.UUID(cursor))
            idx += 1
        q += f" ORDER BY created_at DESC LIMIT ${idx}"
        params.append(limit)
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(q, *params)
        return self._rows(rows)

    async def create(
        self,
        user_id: uuid.UUID,
        token_hash: str,
        expires_at: datetime,
    ) -> dict[str, Any]:
        """Persist a new refresh token record.

        Args:
            user_id:    The owning user's UUID.
            token_hash: SHA-256 hex digest of the raw refresh token.
            expires_at: Absolute expiry timestamp (timezone-aware).

        Returns:
            The inserted row as a dict.
        """
        data: dict[str, Any] = {
            "id": uuid.uuid4(),
            "user_id": user_id,
            "token_hash": token_hash,
            "expires_at": expires_at,
        }
        query, values = self._safe_insert("refresh_tokens", _ALLOWED_INSERT, data)
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, *values)
        return dict(row)  # type: ignore[arg-type]

    async def update(
        self, id: str | uuid.UUID, data: dict[str, Any]
    ) -> dict[str, Any] | None:
        raise NotImplementedError(
            "RefreshTokens are immutable after creation; use revoke() instead."
        )

    async def soft_delete(self, id: str | uuid.UUID) -> bool:
        raise NotImplementedError(
            "RefreshTokens are not soft-deleted; use revoke() instead."
        )

    async def get_active_by_hash(self, token_hash: str) -> dict[str, Any] | None:
        """Fetch a refresh token by its SHA-256 hash.

        Returns the row only if it has not been revoked or expired.
        """
        now = datetime.now(tz=timezone.utc)
        q = (
            "SELECT * FROM refresh_tokens "
            "WHERE token_hash = $1 AND revoked_at IS NULL AND expires_at > $2"
        )
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(q, token_hash, now)
        return self._row(row)

    async def get_by_hash(self, token_hash: str) -> dict[str, Any] | None:
        """Fetch any refresh token by hash (including revoked/expired)."""
        q = "SELECT * FROM refresh_tokens WHERE token_hash = $1"
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(q, token_hash)
        return self._row(row)

    async def revoke(
        self,
        token_id: uuid.UUID,
        *,
        replaced_by_id: uuid.UUID | None = None,
    ) -> None:
        """Mark a single token as revoked.

        Args:
            token_id:       The ID of the token to revoke.
            replaced_by_id: Optional ID of the new token that replaced this one.
        """
        now = datetime.now(tz=timezone.utc)
        if replaced_by_id is not None:
            q = (
                "UPDATE refresh_tokens SET revoked_at = $1, replaced_by_id = $2 "
                "WHERE id = $3"
            )
            async with self._pool.acquire() as conn:
                await conn.execute(q, now, replaced_by_id, token_id)
        else:
            q = "UPDATE refresh_tokens SET revoked_at = $1 WHERE id = $2"
            async with self._pool.acquire() as conn:
                await conn.execute(q, now, token_id)

    async def revoke_all_for_user(self, user_id: uuid.UUID) -> int:
        """Revoke all active refresh tokens for a user (family invalidation).

        Args:
            user_id: The user whose tokens should all be revoked.

        Returns:
            Number of tokens revoked.
        """
        now = datetime.now(tz=timezone.utc)
        q = (
            "UPDATE refresh_tokens SET revoked_at = $1 "
            "WHERE user_id = $2 AND revoked_at IS NULL "
            "RETURNING id"
        )
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(q, now, user_id)
        count = len(rows)
        if count:
            logger.warning(
                "refresh_token.family_revoked",
                user_id=str(user_id),
                count=count,
            )
        return count

    async def get_family_chain(self, token_id: uuid.UUID) -> list[dict[str, Any]]:
        """Walk the replaced_by_id chain to collect the token family.

        Used for reuse detection to find all tokens in a rotation chain.
        Stops after 20 hops to bound query depth.
        """
        results: list[dict[str, Any]] = []
        current_id = token_id
        seen: set[str] = set()
        for _ in range(20):
            key = str(current_id)
            if key in seen:
                break
            seen.add(key)
            q = "SELECT * FROM refresh_tokens WHERE id = $1"
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(q, current_id)
            if row is None:
                break
            record = dict(row)
            results.append(record)
            if record.get("replaced_by_id") is None:
                break
            current_id = record["replaced_by_id"]
        return results
