"""Cursor-based pagination utilities for ForgeGuard API endpoints (WO-031).

Encodes and decodes an opaque pagination cursor that wraps a (created_at, id)
composite key used for keyset pagination on descending time-ordered queries.
"""

from __future__ import annotations

import base64
import uuid
from datetime import datetime, timezone

from forgeguard.core.exceptions import BadRequestError


def encode_cursor(created_at: datetime, record_id: uuid.UUID) -> str:
    """Encode a (created_at, id) pair as an opaque base64 cursor string.

    Args:
        created_at: Timestamp of the last record on the current page.
        record_id:  UUID of the last record on the current page.

    Returns:
        A base64-encoded opaque string safe to embed in query parameters.
    """
    raw = f"{created_at.isoformat()}|{record_id}"
    return base64.b64encode(raw.encode()).decode()


def decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    """Decode an opaque cursor string to a (created_at, id) pair.

    Args:
        cursor: The base64-encoded cursor from a previous response.

    Returns:
        Tuple of (created_at datetime with UTC timezone, record UUID).

    Raises:
        BadRequestError: If the cursor is malformed, corrupted, or tampered with.
    """
    try:
        raw = base64.b64decode(cursor.encode()).decode()
        ts_str, id_str = raw.rsplit("|", 1)
        ts = datetime.fromisoformat(ts_str)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts, uuid.UUID(id_str)
    except Exception as exc:
        raise BadRequestError(
            "Invalid pagination cursor: malformed or corrupted value."
        ) from exc
