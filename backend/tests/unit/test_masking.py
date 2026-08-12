"""Unit tests for core/masking.py mask_ip_address (WO-029).

Coverage:
  - IPv4: last two octets masked as 'xxx.xxx'
  - IPv4 edge values (0.0.0.0, 255.255.255.255, single-digit octets)
  - IPv6 full form: last 5 groups masked as 'xxxx'
  - IPv6 shorthand (::): returns 'masked' (ambiguous)
  - Localhost IPv4 (127.0.0.1): masked like any other IPv4
  - Localhost IPv6 (::1): returns 'masked' (shorthand)
  - None input: returns 'unknown'
  - Empty string: returns 'unknown'
  - Malformed / unrecognised: returns 'masked'
  - Determinism: same input always produces same output
"""

from __future__ import annotations

import pytest

from forgeguard.core.masking import mask_ip_address


# ---------------------------------------------------------------------------
# IPv4
# ---------------------------------------------------------------------------

class TestIPv4Masking:
    def test_typical_private_address(self):
        assert mask_ip_address("192.168.1.100") == "192.168.xxx.xxx"

    def test_all_zero_address(self):
        assert mask_ip_address("0.0.0.0") == "0.0.xxx.xxx"

    def test_all_max_address(self):
        assert mask_ip_address("255.255.255.255") == "255.255.xxx.xxx"

    def test_single_digit_octets(self):
        assert mask_ip_address("10.0.0.1") == "10.0.xxx.xxx"

    def test_loopback(self):
        # 127.0.0.1 is treated as any IPv4 address
        assert mask_ip_address("127.0.0.1") == "127.0.xxx.xxx"

    def test_public_address(self):
        assert mask_ip_address("203.0.113.42") == "203.0.xxx.xxx"

    def test_only_first_two_octets_preserved(self):
        result = mask_ip_address("1.2.3.4")
        assert result == "1.2.xxx.xxx"
        parts = result.split(".")
        assert parts[0] == "1"
        assert parts[1] == "2"
        assert parts[2] == "xxx"
        assert parts[3] == "xxx"


# ---------------------------------------------------------------------------
# IPv6
# ---------------------------------------------------------------------------

class TestIPv6Masking:
    def test_full_form_8_groups(self):
        result = mask_ip_address("2001:db8:85a3:0000:0000:8a2e:0370:7334")
        # First 3 groups preserved, last 5 masked
        assert result == "2001:db8:85a3:xxxx:xxxx:xxxx:xxxx:xxxx"

    def test_all_zeros_full_form(self):
        result = mask_ip_address("0000:0000:0000:0000:0000:0000:0000:0001")
        assert result == "0000:0000:0000:xxxx:xxxx:xxxx:xxxx:xxxx"

    def test_shorthand_notation_fully_masked(self):
        # :: notation is ambiguous — return 'masked'
        assert mask_ip_address("::1") == "masked"

    def test_shorthand_loopback_masked(self):
        assert mask_ip_address("::1") == "masked"

    def test_shorthand_double_colon_other_forms(self):
        assert mask_ip_address("2001:db8::1") == "masked"
        assert mask_ip_address("::") == "masked"

    def test_wrong_group_count_masked(self):
        # Not 8 groups and no :: → malformed
        assert mask_ip_address("2001:db8:85a3") == "masked"


# ---------------------------------------------------------------------------
# Edge / invalid inputs
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_none_returns_unknown(self):
        assert mask_ip_address(None) == "unknown"

    def test_empty_string_returns_unknown(self):
        assert mask_ip_address("") == "unknown"

    def test_whitespace_only_returns_unknown(self):
        assert mask_ip_address("   ") == "unknown"

    def test_garbage_returns_masked(self):
        assert mask_ip_address("not.an.ip") == "masked"

    def test_hostname_returns_masked(self):
        assert mask_ip_address("example.com") == "masked"

    def test_integer_input_returns_masked(self):
        # Non-str, non-None
        assert mask_ip_address(12345) == "masked"  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_same_input_same_output(self):
        ip = "192.168.1.100"
        assert mask_ip_address(ip) == mask_ip_address(ip)

    def test_idempotent_on_already_masked(self):
        masked = mask_ip_address("10.20.30.40")
        assert masked == "10.20.xxx.xxx"
        # Calling again on the masked string should return 'masked' (not a valid IP)
        second = mask_ip_address(masked)
        assert second == "masked"
