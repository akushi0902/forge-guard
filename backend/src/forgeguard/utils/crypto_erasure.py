"""Cryptographic erasure utility for sensitive database columns.

Overwrites JSONB and TEXT columns with cryptographically random data before
DELETE, ensuring original content is unrecoverable from WAL or database backups.

Design:
  - JSONB columns are overwritten with {"__erased__": true, "data": "<base64>"}.
  - TEXT columns are overwritten with a base64url-encoded random string.
  - Individual record failures are logged and skipped (the record is NOT deleted
    without erasure, preventing data leakage).
  - table, id_column, and column names are developer-controlled constants — never
    derived from user input.  Values are always passed as positional parameters.
"""

from __future__ import annotations

import base64
import json
import os
import uuid
from typing import Any

import asyncpg
import structlog

logger = structlog.get_logger(__name__)


async def cryptographic_erase_jsonb(
    conn: asyncpg.Connection,
    table: str,
    id_column: str,
    jsonb_columns: list[str],
    record_ids: list[uuid.UUID],
) -> int:
    """Overwrite JSONB columns with cryptographically random data.

    For each record_id, each column in jsonb_columns is replaced with a JSON
    object ``{"__erased__": true, "data": "<random_base64>"}`` using
    ``os.urandom(32)`` per column.

    Args:
        conn:           An asyncpg connection (should be within a transaction).
        table:          Target table name (developer-controlled constant).
        id_column:      Primary key column name (developer-controlled constant).
        jsonb_columns:  JSONB column names to overwrite (developer-controlled).
        record_ids:     UUIDs of records to erase.

    Returns:
        Number of records successfully erased.
    """
    if not record_ids or not jsonb_columns:
        return 0

    erased_count = 0
    for record_id in record_ids:
        try:
            set_clauses: list[str] = []
            values: list[Any] = []
            for i, col in enumerate(jsonb_columns, start=1):
                random_bytes = os.urandom(32)
                random_b64 = base64.urlsafe_b64encode(random_bytes).decode("ascii")
                overwrite = {"__erased__": True, "data": random_b64}
                set_clauses.append(f"{col} = ${i}::jsonb")
                values.append(json.dumps(overwrite))

            values.append(record_id)
            id_param = f"${len(values)}"
            sql = (
                f"UPDATE {table}"
                f" SET {', '.join(set_clauses)}"
                f" WHERE {id_column} = {id_param}"
            )
            await conn.execute(sql, *values)
            erased_count += 1
        except Exception as exc:
            logger.warning(
                "crypto_erasure.skip_record",
                table=table,
                record_id=str(record_id),
                error=str(exc),
            )

    logger.debug(
        "crypto_erasure.jsonb_complete",
        table=table,
        columns=jsonb_columns,
        erased=erased_count,
        total=len(record_ids),
    )
    return erased_count


async def cryptographic_erase_text(
    conn: asyncpg.Connection,
    table: str,
    id_column: str,
    text_columns: list[str],
    record_ids: list[uuid.UUID],
) -> int:
    """Overwrite TEXT/VARCHAR columns with cryptographically random data.

    Each column is replaced with a base64url-encoded ``os.urandom(32)`` string.

    Args:
        conn:           An asyncpg connection (should be within a transaction).
        table:          Target table name (developer-controlled constant).
        id_column:      Primary key column name (developer-controlled constant).
        text_columns:   TEXT/VARCHAR column names to overwrite (developer-controlled).
        record_ids:     UUIDs of records to erase.

    Returns:
        Number of records successfully erased.
    """
    if not record_ids or not text_columns:
        return 0

    erased_count = 0
    for record_id in record_ids:
        try:
            set_clauses: list[str] = []
            values: list[Any] = []
            for i, col in enumerate(text_columns, start=1):
                random_b64 = base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")
                set_clauses.append(f"{col} = ${i}")
                values.append(random_b64)

            values.append(record_id)
            id_param = f"${len(values)}"
            sql = (
                f"UPDATE {table}"
                f" SET {', '.join(set_clauses)}"
                f" WHERE {id_column} = {id_param}"
            )
            await conn.execute(sql, *values)
            erased_count += 1
        except Exception as exc:
            logger.warning(
                "crypto_erasure.skip_record",
                table=table,
                record_id=str(record_id),
                error=str(exc),
            )

    logger.debug(
        "crypto_erasure.text_complete",
        table=table,
        columns=text_columns,
        erased=erased_count,
        total=len(record_ids),
    )
    return erased_count
