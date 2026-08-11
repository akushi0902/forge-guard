"""Abstract BaseRepository with async CRUD using asyncpg parameterized queries."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from typing import Any

import asyncpg
import structlog

logger = structlog.get_logger(__name__)


class BaseRepository(ABC):
    """Async CRUD base class backed by an asyncpg connection pool.

    All SQL values are passed as asyncpg positional parameters ($1, $2 …) —
    zero string interpolation of caller-supplied values.  Column names that
    appear in dynamic SET/INSERT clauses are validated against developer-defined
    frozensets in each subclass before being included in the SQL string.
    """

    _table: str

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    # ------------------------------------------------------------------
    # Abstract CRUD interface
    # ------------------------------------------------------------------

    @abstractmethod
    async def get_by_id(
        self, id: str | uuid.UUID, *, include_deleted: bool = False
    ) -> dict[str, Any] | None: ...

    @abstractmethod
    async def list(
        self,
        *,
        filters: dict[str, Any] | None = None,
        cursor: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]: ...

    @abstractmethod
    async def create(self, data: dict[str, Any]) -> dict[str, Any]: ...

    @abstractmethod
    async def update(
        self, id: str | uuid.UUID, data: dict[str, Any]
    ) -> dict[str, Any] | None: ...

    @abstractmethod
    async def soft_delete(self, id: str | uuid.UUID) -> bool: ...

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row(record: asyncpg.Record | None) -> dict[str, Any] | None:
        return dict(record) if record is not None else None

    @staticmethod
    def _rows(records: list[asyncpg.Record]) -> list[dict[str, Any]]:
        return [dict(r) for r in records]

    @staticmethod
    def _safe_update_clause(
        allowed: frozenset[str], data: dict[str, Any]
    ) -> tuple[str, list[Any]]:
        """Build a parameterized SET clause restricted to developer-defined columns.

        Column names are drawn from the caller-controlled ``allowed`` frozenset
        so they are never user-supplied.  Values are returned separately for
        positional binding — no value is interpolated into the SQL string.

        Returns an empty string and empty list when no allowed keys are present
        in ``data``.
        """
        filtered = [(col, val) for col, val in data.items() if col in allowed]
        if not filtered:
            return "", []
        set_parts = [f"{col} = ${i + 1}" for i, (col, _) in enumerate(filtered)]
        values = [val for _, val in filtered]
        return ", ".join(set_parts), values

    @staticmethod
    def _safe_insert(
        table: str, allowed: frozenset[str], data: dict[str, Any]
    ) -> tuple[str, list[Any]]:
        """Build a parameterized INSERT … RETURNING * restricted to allowed columns.

        Column names come from ``allowed`` (developer constant); values are
        positional parameters — zero interpolation of caller-supplied values.
        """
        filtered = [(col, val) for col, val in data.items() if col in allowed]
        if not filtered:
            raise ValueError(f"No allowed columns found in data for table {table!r}")
        col_names = ", ".join(col for col, _ in filtered)
        placeholders = ", ".join(f"${i + 1}" for i in range(len(filtered)))
        values = [val for _, val in filtered]
        query = f"INSERT INTO {table} ({col_names}) VALUES ({placeholders}) RETURNING *"
        return query, values
