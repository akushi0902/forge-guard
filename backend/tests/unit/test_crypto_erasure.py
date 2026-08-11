"""Unit tests for the cryptographic erasure utility (WO-032).

Tests verify that:
- JSONB columns are overwritten with random marker objects (not original data).
- TEXT columns are overwritten with base64url-encoded random strings.
- Empty inputs return 0 without calling the database.
- A failure on one record is skipped and does not stop processing of others.
- Each overwrite uses fresh randomness (two calls produce different values).

All tests use AsyncMock connections — no database required.
"""

from __future__ import annotations

import base64
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from forgeguard.utils.crypto_erasure import (
    cryptographic_erase_jsonb,
    cryptographic_erase_text,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_conn() -> AsyncMock:
    """Return a mock asyncpg Connection with execute as an AsyncMock."""
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    return conn


def _make_ids(n: int = 3) -> list[uuid.UUID]:
    return [uuid.uuid4() for _ in range(n)]


# ---------------------------------------------------------------------------
# cryptographic_erase_jsonb
# ---------------------------------------------------------------------------

class TestCryptographicEraseJsonb:

    @pytest.mark.asyncio
    async def test_returns_zero_for_empty_record_ids(self):
        conn = _make_conn()
        result = await cryptographic_erase_jsonb(conn, "t", "id", ["col"], [])
        assert result == 0
        conn.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_zero_for_empty_columns(self):
        conn = _make_conn()
        ids = _make_ids(2)
        result = await cryptographic_erase_jsonb(conn, "t", "id", [], ids)
        assert result == 0
        conn.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_called_once_per_record(self):
        conn = _make_conn()
        ids = _make_ids(3)
        await cryptographic_erase_jsonb(conn, "assessment_scores", "id", ["dimension_scores"], ids)
        assert conn.execute.call_count == 3

    @pytest.mark.asyncio
    async def test_returns_erased_count_on_success(self):
        conn = _make_conn()
        ids = _make_ids(4)
        result = await cryptographic_erase_jsonb(conn, "t", "id", ["col"], ids)
        assert result == 4

    @pytest.mark.asyncio
    async def test_overwrite_is_valid_json_with_erased_marker(self):
        """The value written to the JSONB column must be a JSON string with __erased__."""
        captured_args: list[tuple] = []

        async def capture(*args):
            captured_args.append(args)

        conn = _make_conn()
        conn.execute = capture
        ids = [uuid.uuid4()]

        await cryptographic_erase_jsonb(conn, "assessment_scores", "id", ["dimension_scores"], ids)

        assert len(captured_args) == 1
        # args[0] = SQL, args[1] = json_str, args[2] = record_id
        sql, json_str, _record_id = captured_args[0]
        overwrite = json.loads(json_str)
        assert overwrite.get("__erased__") is True
        assert "data" in overwrite
        # data must be valid base64url
        base64.urlsafe_b64decode(overwrite["data"] + "==")

    @pytest.mark.asyncio
    async def test_original_content_not_present_after_overwrite(self):
        """The overwrite value must not contain the original field name or typical values."""
        captured_args: list[tuple] = []

        async def capture(*args):
            captured_args.append(args)

        conn = _make_conn()
        conn.execute = capture
        ids = [uuid.uuid4()]

        await cryptographic_erase_jsonb(
            conn, "assessment_scores", "id",
            ["dimension_scores", "contributing_factors"], ids
        )

        # One execute call with two columns.
        assert len(captured_args) == 1
        sql = captured_args[0][0]
        # SQL should reference both columns.
        assert "dimension_scores" in sql
        assert "contributing_factors" in sql
        # Neither original value should appear in the written JSON values.
        for arg in captured_args[0][1:-1]:  # skip last (record_id)
            parsed = json.loads(arg)
            assert "security" not in parsed
            assert "test_coverage" not in parsed

    @pytest.mark.asyncio
    async def test_each_record_gets_unique_random_data(self):
        """Two records must receive different random overwrite values."""
        written_data: list[str] = []

        async def capture(*args):
            # args[1] is the JSON string
            parsed = json.loads(args[1])
            written_data.append(parsed["data"])

        conn = _make_conn()
        conn.execute = capture
        ids = _make_ids(2)

        await cryptographic_erase_jsonb(conn, "t", "id", ["col"], ids)
        assert len(written_data) == 2
        assert written_data[0] != written_data[1]

    @pytest.mark.asyncio
    async def test_single_record_failure_is_skipped(self):
        """A failure on one record should not block others."""
        call_count = 0

        async def fail_first(*args):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("DB error")

        conn = _make_conn()
        conn.execute = fail_first
        ids = _make_ids(3)

        result = await cryptographic_erase_jsonb(conn, "t", "id", ["col"], ids)
        # First record failed, remaining two succeeded.
        assert result == 2
        assert call_count == 3


# ---------------------------------------------------------------------------
# cryptographic_erase_text
# ---------------------------------------------------------------------------

class TestCryptographicEraseText:

    @pytest.mark.asyncio
    async def test_returns_zero_for_empty_record_ids(self):
        conn = _make_conn()
        result = await cryptographic_erase_text(conn, "t", "id", ["col"], [])
        assert result == 0
        conn.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_zero_for_empty_columns(self):
        conn = _make_conn()
        ids = _make_ids(2)
        result = await cryptographic_erase_text(conn, "t", "id", [], ids)
        assert result == 0
        conn.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_called_once_per_record(self):
        conn = _make_conn()
        ids = _make_ids(3)
        await cryptographic_erase_text(conn, "release_decisions", "id", ["rationale", "comment"], ids)
        assert conn.execute.call_count == 3

    @pytest.mark.asyncio
    async def test_returns_erased_count_on_success(self):
        conn = _make_conn()
        ids = _make_ids(5)
        result = await cryptographic_erase_text(conn, "t", "id", ["col"], ids)
        assert result == 5

    @pytest.mark.asyncio
    async def test_overwrite_value_is_valid_base64url(self):
        """The overwrite value must be valid base64url-encoded data."""
        captured_args: list[tuple] = []

        async def capture(*args):
            captured_args.append(args)

        conn = _make_conn()
        conn.execute = capture
        ids = [uuid.uuid4()]

        await cryptographic_erase_text(conn, "release_decisions", "id", ["rationale"], ids)

        assert len(captured_args) == 1
        # args[0] = SQL, args[1] = random_b64, args[2] = record_id
        _sql, random_b64, _record_id = captured_args[0]
        # Must be decodable as base64url
        base64.urlsafe_b64decode(random_b64 + "==")
        # Must not look like real text
        assert "sql" not in random_b64.lower()
        assert "rationale" not in random_b64.lower()

    @pytest.mark.asyncio
    async def test_each_record_gets_unique_random_data(self):
        """Two records must receive different random overwrite values."""
        written_values: list[str] = []

        async def capture(*args):
            # args[1] is the overwrite string
            written_values.append(args[1])

        conn = _make_conn()
        conn.execute = capture
        ids = _make_ids(2)

        await cryptographic_erase_text(conn, "t", "id", ["col"], ids)
        assert len(written_values) == 2
        assert written_values[0] != written_values[1]

    @pytest.mark.asyncio
    async def test_multi_column_overwrite_uses_different_random_per_column(self):
        """Each TEXT column within a single record gets its own random value."""
        captured_args: list[tuple] = []

        async def capture(*args):
            captured_args.append(args)

        conn = _make_conn()
        conn.execute = capture
        ids = [uuid.uuid4()]
        columns = ["rationale", "comment"]

        await cryptographic_erase_text(conn, "release_decisions", "id", columns, ids)

        assert len(captured_args) == 1
        # SQL has $1 and $2 placeholders for the two columns.
        sql = captured_args[0][0]
        assert "$1" in sql
        assert "$2" in sql
        val1, val2 = captured_args[0][1], captured_args[0][2]
        assert val1 != val2

    @pytest.mark.asyncio
    async def test_single_record_failure_is_skipped(self):
        call_count = 0

        async def fail_first(*args):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("DB error")

        conn = _make_conn()
        conn.execute = fail_first
        ids = _make_ids(4)

        result = await cryptographic_erase_text(conn, "t", "id", ["col"], ids)
        assert result == 3
        assert call_count == 4
