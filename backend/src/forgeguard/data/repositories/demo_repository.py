"""DemoTransactionRepository: async CRUD for the demo_transactions table."""

from __future__ import annotations

import uuid
from typing import Any

import asyncpg
import structlog

from forgeguard.data.repositories.base import BaseRepository

logger = structlog.get_logger(__name__)

_ALLOWED_INSERT: frozenset[str] = frozenset({
    "id", "amount", "currency", "merchant", "card_last_four",
    "status", "authorization_code", "metadata",
})

_PAYMENT_SERVICE_ID = uuid.UUID("d0000000-0000-0000-0000-000000000001")


class DemoTransactionRepository(BaseRepository):
    _table = "demo_transactions"

    async def get_by_id(
        self, id: str | uuid.UUID, *, include_deleted: bool = False
    ) -> dict[str, Any] | None:
        q = "SELECT * FROM demo_transactions WHERE id = $1"
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
        q = "SELECT * FROM demo_transactions WHERE TRUE"
        if cursor:
            q += f" AND id > ${idx}"
            params.append(uuid.UUID(cursor))
            idx += 1
        q += f" ORDER BY created_at DESC LIMIT ${idx}"
        params.append(limit)
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(q, *params)
        return self._rows(rows)

    async def create(self, data: dict[str, Any]) -> dict[str, Any]:
        query, values = self._safe_insert("demo_transactions", _ALLOWED_INSERT, data)
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, *values)
        return dict(row)  # type: ignore[arg-type]

    async def update(
        self, id: str | uuid.UUID, data: dict[str, Any]
    ) -> dict[str, Any] | None:
        raise NotImplementedError(
            "Demo transactions are immutable after creation."
        )

    async def soft_delete(self, id: str | uuid.UUID) -> bool:
        raise NotImplementedError(
            "Demo transactions are not soft-deleted; use delete_all_demo_transactions()."
        )

    async def delete_all_demo_transactions(self) -> int:
        """Delete all demo transactions and return the count purged."""
        q = "DELETE FROM demo_transactions RETURNING id"
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(q)
        count = len(rows)
        logger.info("demo_transactions_purged", count=count)
        return count

    async def get_demo_service_info(
        self, service_id: uuid.UUID | None = None
    ) -> dict[str, Any] | None:
        """Fetch the Payment Service record from the services table."""
        target = service_id if service_id is not None else _PAYMENT_SERVICE_ID
        q = "SELECT * FROM services WHERE id = $1 AND deleted_at IS NULL"
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(q, target)
        return self._row(row)
