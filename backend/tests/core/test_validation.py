"""Tests for ForgeGuardBaseModel and reusable field types.

Covers:
    1. Strict mode: string where int expected is rejected.
    2. Extra fields are forbidden.
    3. Missing required fields produce clear errors.
    4. str_strip_whitespace strips leading/trailing whitespace.
    5. UUIDField — valid/invalid patterns.
    6. CommitSHAField — valid/invalid (length and charset).
    7. EmailField — valid/invalid patterns.
    8. ScoreField — valid range, below 0, above 100.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from forgeguard.core.validation import (
    CommitSHAField,
    EmailField,
    ForgeGuardBaseModel,
    ScoreField,
    UUIDField,
)


# ---------------------------------------------------------------------------
# Sample models for tests
# ---------------------------------------------------------------------------

class _StrictInt(ForgeGuardBaseModel):
    count: int


class _WithDefault(ForgeGuardBaseModel):
    name: str
    score: float = 0.0


class _WithUUID(ForgeGuardBaseModel):
    repo_id: UUIDField  # type: ignore[valid-type]


class _WithCommitSHA(ForgeGuardBaseModel):
    sha: CommitSHAField  # type: ignore[valid-type]


class _WithEmail(ForgeGuardBaseModel):
    email: EmailField  # type: ignore[valid-type]


class _WithScore(ForgeGuardBaseModel):
    score: ScoreField  # type: ignore[valid-type]


# ---------------------------------------------------------------------------
# ForgeGuardBaseModel — strict mode
# ---------------------------------------------------------------------------

class TestStrictMode:
    def test_string_rejected_for_int_field(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            _StrictInt(count="42")  # type: ignore[arg-type]
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("count",) for e in errors)

    def test_float_rejected_for_int_field(self) -> None:
        with pytest.raises(ValidationError):
            _StrictInt(count=3.14)  # type: ignore[arg-type]

    def test_correct_int_accepted(self) -> None:
        m = _StrictInt(count=5)
        assert m.count == 5


# ---------------------------------------------------------------------------
# ForgeGuardBaseModel — extra fields
# ---------------------------------------------------------------------------

class TestExtraFields:
    def test_extra_field_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            _StrictInt(count=1, unexpected_field="oops")  # type: ignore[call-arg]
        errors = exc_info.value.errors()
        assert any("extra" in e["type"] for e in errors)

    def test_no_extra_fields_accepted(self) -> None:
        m = _StrictInt(count=99)
        assert m.count == 99


# ---------------------------------------------------------------------------
# ForgeGuardBaseModel — required fields
# ---------------------------------------------------------------------------

class TestRequiredFields:
    def test_missing_required_field_raises(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            _WithDefault()  # type: ignore[call-arg]  # 'name' is required
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("name",) for e in errors)

    def test_optional_field_has_default(self) -> None:
        m = _WithDefault(name="test")
        assert m.score == 0.0


# ---------------------------------------------------------------------------
# ForgeGuardBaseModel — whitespace stripping
# ---------------------------------------------------------------------------

class TestWhitespaceStripping:
    def test_leading_trailing_whitespace_stripped(self) -> None:
        m = _WithDefault(name="  hello  ")
        assert m.name == "hello"

    def test_internal_whitespace_preserved(self) -> None:
        m = _WithDefault(name="hello world")
        assert m.name == "hello world"


# ---------------------------------------------------------------------------
# UUIDField
# ---------------------------------------------------------------------------

class TestUUIDField:
    def test_valid_uuid_accepted(self) -> None:
        m = _WithUUID(repo_id="550e8400-e29b-41d4-a716-446655440000")
        assert m.repo_id == "550e8400-e29b-41d4-a716-446655440000"

    def test_uuid_without_hyphens_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _WithUUID(repo_id="550e8400e29b41d4a716446655440000")

    def test_non_hex_uuid_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _WithUUID(repo_id="zzzzzzzz-zzzz-zzzz-zzzz-zzzzzzzzzzzz")

    def test_empty_string_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _WithUUID(repo_id="")

    def test_too_short_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _WithUUID(repo_id="550e8400-e29b-41d4-a716")


# ---------------------------------------------------------------------------
# CommitSHAField
# ---------------------------------------------------------------------------

_VALID_SHA = "a" * 40


class TestCommitSHAField:
    def test_valid_sha_accepted(self) -> None:
        m = _WithCommitSHA(sha=_VALID_SHA)
        assert m.sha == _VALID_SHA

    def test_hex_digits_accepted(self) -> None:
        sha = "0123456789abcdef" * 2 + "01234567"
        m = _WithCommitSHA(sha=sha)
        assert len(m.sha) == 40

    def test_too_short_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _WithCommitSHA(sha="abc123")

    def test_too_long_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _WithCommitSHA(sha="a" * 41)

    def test_uppercase_hex_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _WithCommitSHA(sha="A" * 40)

    def test_non_hex_chars_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _WithCommitSHA(sha="g" * 40)


# ---------------------------------------------------------------------------
# EmailField
# ---------------------------------------------------------------------------

class TestEmailField:
    def test_valid_email_accepted(self) -> None:
        m = _WithEmail(email="user@example.com")
        assert m.email == "user@example.com"

    def test_subaddress_accepted(self) -> None:
        m = _WithEmail(email="user+tag@example.co.uk")
        assert "user+tag" in m.email

    def test_missing_at_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _WithEmail(email="userexample.com")

    def test_missing_domain_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _WithEmail(email="user@")

    def test_missing_tld_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _WithEmail(email="user@example")

    def test_empty_string_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _WithEmail(email="")


# ---------------------------------------------------------------------------
# ScoreField
# ---------------------------------------------------------------------------

class TestScoreField:
    def test_zero_accepted(self) -> None:
        m = _WithScore(score=0.0)
        assert m.score == 0.0

    def test_hundred_accepted(self) -> None:
        m = _WithScore(score=100.0)
        assert m.score == 100.0

    def test_midrange_accepted(self) -> None:
        m = _WithScore(score=85.5)
        assert m.score == 85.5

    def test_below_zero_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _WithScore(score=-0.1)

    def test_above_hundred_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _WithScore(score=100.1)

    def test_string_rejected_strict(self) -> None:
        with pytest.raises(ValidationError):
            _WithScore(score="85")  # type: ignore[arg-type]
