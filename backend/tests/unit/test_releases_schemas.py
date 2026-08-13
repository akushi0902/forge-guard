"""Unit tests for Release Assessment Pydantic schemas (WO-048).

Covers:
  - ReleaseAssessmentRequest validation (SHA format, UUID, at-least-one-of)
  - Cursor encode/decode round-trip
  - Response model construction
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from forgeguard.api.schemas.releases import (
    ReleaseAssessmentRequest,
    decode_cursor,
    encode_cursor,
)


# ---------------------------------------------------------------------------
# ReleaseAssessmentRequest
# ---------------------------------------------------------------------------


class TestReleaseAssessmentRequest:
    def test_valid_with_commit_sha(self) -> None:
        req = ReleaseAssessmentRequest(
            service_id=uuid.uuid4(),
            commit_sha="a" * 40,
        )
        assert req.commit_sha == "a" * 40

    def test_valid_with_pr_reference(self) -> None:
        req = ReleaseAssessmentRequest(
            service_id=uuid.uuid4(),
            pr_reference="https://github.com/org/repo/pull/123",
        )
        assert req.pr_reference is not None

    def test_valid_with_both_fields(self) -> None:
        req = ReleaseAssessmentRequest(
            service_id=uuid.uuid4(),
            commit_sha="b" * 40,
            pr_reference="PR-456",
        )
        assert req.commit_sha is not None
        assert req.pr_reference is not None

    def test_missing_both_fields_raises(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            ReleaseAssessmentRequest(service_id=uuid.uuid4())
        assert "at least one" in str(exc_info.value).lower()

    def test_invalid_sha_length_raises(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            ReleaseAssessmentRequest(
                service_id=uuid.uuid4(),
                commit_sha="abc123",
            )
        assert "40-character" in str(exc_info.value)

    def test_sha_with_non_hex_chars_raises(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            ReleaseAssessmentRequest(
                service_id=uuid.uuid4(),
                commit_sha="z" * 40,
            )
        assert "hexadecimal" in str(exc_info.value).lower()

    def test_valid_sha_mixed_case(self) -> None:
        sha = "aAbBcC1234567890" * 2 + "aAbBcCdD"
        req = ReleaseAssessmentRequest(service_id=uuid.uuid4(), commit_sha=sha)
        assert req.commit_sha == sha

    def test_pr_reference_max_length_255(self) -> None:
        req = ReleaseAssessmentRequest(
            service_id=uuid.uuid4(),
            pr_reference="x" * 255,
        )
        assert len(req.pr_reference) == 255

    def test_pr_reference_exceeding_255_raises(self) -> None:
        with pytest.raises(ValidationError):
            ReleaseAssessmentRequest(
                service_id=uuid.uuid4(),
                pr_reference="x" * 256,
            )

    def test_invalid_service_id_raises(self) -> None:
        with pytest.raises(ValidationError):
            ReleaseAssessmentRequest(
                service_id="not-a-uuid",
                commit_sha="a" * 40,
            )

    def test_empty_commit_sha_string_raises(self) -> None:
        with pytest.raises(ValidationError):
            ReleaseAssessmentRequest(
                service_id=uuid.uuid4(),
                commit_sha="",
            )


# ---------------------------------------------------------------------------
# Cursor encode/decode
# ---------------------------------------------------------------------------


class TestCursorEncoding:
    def test_round_trip(self) -> None:
        now = datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        record_id = uuid.uuid4()
        cursor = encode_cursor(now, record_id)
        decoded_ts, decoded_id = decode_cursor(cursor)
        assert decoded_ts == now
        assert decoded_id == record_id

    def test_cursor_is_base64_string(self) -> None:
        cursor = encode_cursor(datetime(2025, 1, 1, tzinfo=timezone.utc), uuid.uuid4())
        # Should be URL-safe base64 (alphanumeric, -, _)
        import re
        assert re.match(r"^[A-Za-z0-9_-]+=*$", cursor)

    def test_invalid_cursor_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Invalid pagination cursor"):
            decode_cursor("not-a-valid-cursor!!!")

    def test_different_records_produce_different_cursors(self) -> None:
        ts = datetime(2025, 6, 1, tzinfo=timezone.utc)
        c1 = encode_cursor(ts, uuid.uuid4())
        c2 = encode_cursor(ts, uuid.uuid4())
        assert c1 != c2
