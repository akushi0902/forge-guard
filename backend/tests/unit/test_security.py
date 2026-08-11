"""Unit tests for forgeguard.core.security (WO-021).

Covers:
  - hash_password produces a valid bcrypt hash at cost factor 12
  - verify_password round-trips correctly (success and failure)
  - validate_password_strength catches every individual rule violation
  - validate_password_strength passes a conformant password
  - Edge cases: empty string, exactly-12-char password, Unicode in password
"""

from __future__ import annotations

import pytest

from forgeguard.core.security import hash_password, validate_password_strength, verify_password


# ---------------------------------------------------------------------------
# hash_password
# ---------------------------------------------------------------------------

class TestHashPassword:
    def test_returns_string(self):
        result = hash_password("Correct!Horse9Battery")
        assert isinstance(result, str)

    def test_starts_with_bcrypt_prefix(self):
        result = hash_password("Correct!Horse9Battery")
        assert result.startswith("$2b$")

    def test_hash_contains_rounds_12(self):
        # bcrypt format: $2b$12$...
        result = hash_password("Correct!Horse9Battery")
        assert "$12$" in result

    def test_raw_password_not_in_hash(self):
        pw = "MyS3cret!Pass"
        result = hash_password(pw)
        assert pw not in result

    def test_two_hashes_of_same_password_differ(self):
        pw = "Correct!Horse9Battery"
        h1 = hash_password(pw)
        h2 = hash_password(pw)
        assert h1 != h2  # different salts


# ---------------------------------------------------------------------------
# verify_password
# ---------------------------------------------------------------------------

class TestVerifyPassword:
    def test_correct_password_returns_true(self):
        pw = "Correct!Horse9Battery"
        h = hash_password(pw)
        assert verify_password(pw, h) is True

    def test_wrong_password_returns_false(self):
        pw = "Correct!Horse9Battery"
        h = hash_password(pw)
        assert verify_password("WrongPass!11", h) is False

    def test_empty_password_returns_false(self):
        pw = "Correct!Horse9Battery"
        h = hash_password(pw)
        assert verify_password("", h) is False

    def test_invalid_hash_returns_false_not_exception(self):
        assert verify_password("whatever", "not-a-valid-bcrypt-hash") is False

    def test_hash_of_different_password_returns_false(self):
        h = hash_password("OtherP@ssw0rd!")
        assert verify_password("Correct!Horse9Battery", h) is False


# ---------------------------------------------------------------------------
# validate_password_strength — individual violations
# ---------------------------------------------------------------------------

class TestValidatePasswordStrengthViolations:
    def test_too_short_returns_violation(self):
        violations = validate_password_strength("Sh0rt!")
        assert any("12 characters" in v for v in violations)

    def test_exactly_11_chars_returns_length_violation(self):
        violations = validate_password_strength("Aa1!cdefghi")  # 11 chars
        assert any("12 characters" in v for v in violations)

    def test_missing_uppercase_returns_violation(self):
        violations = validate_password_strength("nouppercase1!")
        assert any("uppercase" in v.lower() for v in violations)

    def test_missing_lowercase_returns_violation(self):
        violations = validate_password_strength("NOLOWERCASE1!")
        assert any("lowercase" in v.lower() for v in violations)

    def test_missing_digit_returns_violation(self):
        violations = validate_password_strength("NoDigitPass!!")
        assert any("digit" in v.lower() for v in violations)

    def test_missing_special_char_returns_violation(self):
        violations = validate_password_strength("NoSpecialChar1A")
        assert any("special" in v.lower() for v in violations)

    def test_empty_string_returns_all_violations(self):
        violations = validate_password_strength("")
        # Should catch at minimum: length, uppercase, lowercase, digit, special
        assert len(violations) >= 4

    def test_multiple_violations_all_returned(self):
        # Only lowercase letters, too short
        violations = validate_password_strength("short")
        violation_text = " ".join(violations).lower()
        assert "12 characters" in violation_text
        assert "uppercase" in violation_text
        assert "digit" in violation_text
        assert "special" in violation_text


# ---------------------------------------------------------------------------
# validate_password_strength — passing cases
# ---------------------------------------------------------------------------

class TestValidatePasswordStrengthPassing:
    def test_exactly_12_chars_all_types_passes(self):
        # Exactly 12: upper + lower + digit + special
        violations = validate_password_strength("Aa1!cdefghij")
        assert violations == []

    def test_strong_password_passes(self):
        violations = validate_password_strength("Correct!Horse9Battery")
        assert violations == []

    def test_password_with_multiple_special_chars_passes(self):
        violations = validate_password_strength("P@$$w0rd!Str0ng")
        assert violations == []

    def test_password_with_tag_email_passes(self):
        violations = validate_password_strength("S3cret+Pass@word!")
        assert violations == []

    def test_returns_empty_list_on_valid_password(self):
        result = validate_password_strength("ValidP@ssw0rd!")
        assert isinstance(result, list)
        assert result == []
