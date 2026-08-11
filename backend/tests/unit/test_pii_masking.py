"""Unit tests for forgeguard.utils.pii_masking.

Covers:
  1. mask_email — standard, single-char local, no-@, empty, None, Unicode.
  2. mask_name  — single word, multi-word, single char, empty, None, Unicode.
  3. mask_ip    — IPv4 standard, IPv4 private, IPv6 full, IPv6 shorthand,
                  unrecognized formats, empty, None.
  4. mask_field — dispatcher routes to correct masking function.
  5. Determinism — calling each function twice with the same input produces
                   identical output.
  6. Edge cases  — very long strings, whitespace-only, malformed inputs.
"""

from __future__ import annotations

import pytest

from forgeguard.utils.pii_masking import (
    PII_FIELD_NAMES,
    mask_email,
    mask_field,
    mask_ip,
    mask_name,
)


# ---------------------------------------------------------------------------
# mask_email
# ---------------------------------------------------------------------------

class TestMaskEmail:
    def test_standard_email(self) -> None:
        assert mask_email("john.doe@example.com") == "j***@example.com"

    def test_preserves_full_domain(self) -> None:
        result = mask_email("alice@mail.corp.example.co.uk")
        assert result == "a***@mail.corp.example.co.uk"

    def test_plus_addressing(self) -> None:
        result = mask_email("user+tag@example.com")
        assert result == "u***@example.com"

    def test_single_char_local(self) -> None:
        result = mask_email("a@example.com")
        assert result == "a***@example.com"

    def test_no_at_sign_returns_masked(self) -> None:
        result = mask_email("not-an-email")
        assert result == "[MASKED]"

    def test_empty_string_returns_empty(self) -> None:
        assert mask_email("") == ""

    def test_none_returns_none(self) -> None:
        assert mask_email(None) is None

    def test_domain_preserved_exactly(self) -> None:
        result = mask_email("bob@EXAMPLE.COM")
        assert result.endswith("@EXAMPLE.COM")

    def test_first_char_preserved(self) -> None:
        result = mask_email("zebra@example.com")
        assert result.startswith("z")

    def test_asterisks_in_local(self) -> None:
        result = mask_email("john@example.com")
        assert "***" in result

    def test_raw_result_format(self) -> None:
        result = mask_email("user@example.com")
        assert "@" in result
        local, domain = result.split("@", 1)
        assert local.endswith("***")
        assert domain == "example.com"

    @pytest.mark.parametrize("email", [
        "short@x.io",
        "test.user@subdomain.example.org",
        "admin+filter@company.com",
    ])
    def test_various_emails(self, email: str) -> None:
        result = mask_email(email)
        assert "@" in result
        assert result != email  # must be masked
        assert result[0] == email[0]  # first char preserved

    def test_unicode_email(self) -> None:
        result = mask_email("üser@example.com")
        assert result == "ü***@example.com"


# ---------------------------------------------------------------------------
# mask_name
# ---------------------------------------------------------------------------

class TestMaskName:
    def test_full_name(self) -> None:
        assert mask_name("John Doe") == "J*** D***"

    def test_single_name(self) -> None:
        assert mask_name("Alice") == "A***"

    def test_single_char_word_unchanged(self) -> None:
        assert mask_name("J") == "J"

    def test_three_word_name(self) -> None:
        result = mask_name("Mary Jane Watson")
        assert result == "M*** J*** W***"

    def test_empty_string_returns_empty(self) -> None:
        assert mask_name("") == ""

    def test_whitespace_only_returns_original(self) -> None:
        result = mask_name("   ")
        # All whitespace — split produces empty list; returns original
        assert result == "   " or result == ""

    def test_none_returns_none(self) -> None:
        assert mask_name(None) is None

    def test_first_char_of_each_word_preserved(self) -> None:
        result = mask_name("John Doe")
        parts = result.split()
        assert parts[0][0] == "J"
        assert parts[1][0] == "D"

    def test_asterisks_after_first_char(self) -> None:
        result = mask_name("Alice")
        assert result == "A***"

    def test_unicode_name(self) -> None:
        result = mask_name("Ångström Björk")
        assert result[0] == "Å"
        parts = result.split()
        assert all("***" in p for p in parts)

    def test_lowercase_name(self) -> None:
        result = mask_name("alice bob")
        parts = result.split()
        assert parts[0] == "a***"
        assert parts[1] == "b***"


# ---------------------------------------------------------------------------
# mask_ip
# ---------------------------------------------------------------------------

class TestMaskIP:
    def test_ipv4_standard(self) -> None:
        assert mask_ip("192.168.1.100") == "192.168.***.***"

    def test_ipv4_private_10(self) -> None:
        assert mask_ip("10.0.0.1") == "10.0.***.***"

    def test_ipv4_private_172(self) -> None:
        assert mask_ip("172.16.0.1") == "172.16.***.***"

    def test_ipv4_loopback(self) -> None:
        assert mask_ip("127.0.0.1") == "127.0.***.***"

    def test_ipv4_preserves_first_two_octets(self) -> None:
        result = mask_ip("203.0.113.42")
        assert result.startswith("203.0.")

    def test_ipv4_last_two_masked(self) -> None:
        result = mask_ip("10.20.30.40")
        assert result == "10.20.***.***"

    def test_ipv6_full_form(self) -> None:
        result = mask_ip("2001:0db8:0000:0000:0000:0000:0000:0001")
        assert result.startswith("2001:0db8:")
        assert "*" in result

    def test_ipv6_full_preserves_first_two_groups(self) -> None:
        result = mask_ip("2001:db8:85a3:0000:0000:8a2e:0370:7334")
        assert result.startswith("2001:db8:")

    def test_ipv6_shorthand_masked(self) -> None:
        assert mask_ip("::1") == "[MASKED_IP]"

    def test_ipv6_shorthand_double_colon_masked(self) -> None:
        assert mask_ip("fe80::1") == "[MASKED_IP]"

    def test_hostname_masked(self) -> None:
        assert mask_ip("hostname.internal") == "[MASKED_IP]"

    def test_empty_string_returns_empty(self) -> None:
        assert mask_ip("") == ""

    def test_none_returns_none(self) -> None:
        assert mask_ip(None) is None

    def test_garbage_returns_masked_ip(self) -> None:
        assert mask_ip("not-an-ip-at-all") == "[MASKED_IP]"

    @pytest.mark.parametrize("ip,expected_prefix", [
        ("192.168.0.1",  "192.168."),
        ("10.0.0.1",     "10.0."),
        ("172.31.0.1",   "172.31."),
        ("203.0.113.1",  "203.0."),
    ])
    def test_ipv4_various(self, ip: str, expected_prefix: str) -> None:
        result = mask_ip(ip)
        assert result.startswith(expected_prefix)
        assert result.endswith("***.***")


# ---------------------------------------------------------------------------
# mask_field
# ---------------------------------------------------------------------------

class TestMaskField:
    def test_email_field(self) -> None:
        result = mask_field("email", "user@example.com")
        assert result == "u***@example.com"

    def test_user_email_field(self) -> None:
        result = mask_field("user_email", "alice@example.com")
        assert result == "a***@example.com"

    def test_actor_email_field(self) -> None:
        result = mask_field("actor_email", "bob@example.com")
        assert result == "b***@example.com"

    def test_name_field(self) -> None:
        result = mask_field("name", "John Doe")
        assert result == "J*** D***"

    def test_full_name_field(self) -> None:
        result = mask_field("full_name", "Jane Smith")
        assert result == "J*** S***"

    def test_ip_address_field(self) -> None:
        result = mask_field("ip_address", "192.168.1.1")
        assert result == "192.168.***.***"

    def test_client_ip_field(self) -> None:
        result = mask_field("client_ip", "10.0.0.5")
        assert result == "10.0.***.***"

    def test_unknown_field_returns_unchanged(self) -> None:
        result = mask_field("some_other_field", "my value")
        assert result == "my value"

    def test_none_value_returns_none(self) -> None:
        result = mask_field("email", None)
        assert result is None

    def test_case_insensitive_field_name(self) -> None:
        result = mask_field("EMAIL", "user@example.com")
        assert result == "u***@example.com"


# ---------------------------------------------------------------------------
# PII_FIELD_NAMES set
# ---------------------------------------------------------------------------

class TestPIIFieldNames:
    def test_email_in_set(self) -> None:
        assert "email" in PII_FIELD_NAMES

    def test_name_in_set(self) -> None:
        assert "name" in PII_FIELD_NAMES

    def test_ip_address_in_set(self) -> None:
        assert "ip_address" in PII_FIELD_NAMES

    def test_is_frozenset(self) -> None:
        assert isinstance(PII_FIELD_NAMES, frozenset)


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

class TestDeterminism:
    @pytest.mark.parametrize("email", [
        "alice@example.com",
        "Bob+tag@sub.domain.co.uk",
        "single@x.io",
    ])
    def test_email_deterministic(self, email: str) -> None:
        assert mask_email(email) == mask_email(email)

    @pytest.mark.parametrize("name", [
        "John Doe",
        "Alice",
        "Mary Jane Watson",
    ])
    def test_name_deterministic(self, name: str) -> None:
        assert mask_name(name) == mask_name(name)

    @pytest.mark.parametrize("ip", [
        "192.168.1.1",
        "10.0.0.1",
        "2001:db8:0:0:0:0:0:1",
    ])
    def test_ip_deterministic(self, ip: str) -> None:
        assert mask_ip(ip) == mask_ip(ip)

    def test_mask_field_deterministic(self) -> None:
        assert mask_field("email", "user@example.com") == mask_field("email", "user@example.com")


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_very_long_email_local(self) -> None:
        long_local = "a" * 500
        email = f"{long_local}@example.com"
        result = mask_email(email)
        # Only first char preserved; result should be short
        assert result == "a***@example.com"

    def test_very_long_name(self) -> None:
        long_name = "Word " * 100
        result = mask_name(long_name.strip())
        # Should not raise; each word is masked
        assert result is not None
        assert "***" in result

    def test_very_long_ip_like_string(self) -> None:
        result = mask_ip("1.2.3.4.5.6.7.8")
        assert result == "[MASKED_IP]"

    def test_email_with_multiple_at_signs(self) -> None:
        # Only first @ is used as split point
        result = mask_email("user@host@example.com")
        # Local is "user", domain is "host@example.com"
        assert result == "u***@host@example.com"

    def test_name_with_extra_spaces(self) -> None:
        # split() handles multiple spaces
        result = mask_name("John   Doe")
        assert result == "J*** D***"
