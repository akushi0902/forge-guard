"""Unit tests for core.ip_masking.mask_ip_address (WO-019).

Tests cover:
  - IPv4 masking (last octet replaced with 'xxx')
  - IPv6 masking (last 4 groups replaced with 'xxxx')
  - Empty string → 'unknown'
  - None input → 'unknown'
  - Malformed IP → 'masked'
  - localhost (127.0.0.1) → '127.0.0.xxx'
  - IPv6 shorthand (::1) → 'masked'
  - Determinism: same input always yields same output
"""

from __future__ import annotations

import pytest

from forgeguard.core.ip_masking import mask_ip_address


class TestIPv4Masking:
    def test_standard_address(self):
        assert mask_ip_address("192.168.1.100") == "192.168.1.xxx"

    def test_preserves_first_three_octets(self):
        result = mask_ip_address("10.20.30.40")
        assert result == "10.20.30.xxx"

    def test_localhost(self):
        assert mask_ip_address("127.0.0.1") == "127.0.0.xxx"

    def test_public_ip(self):
        assert mask_ip_address("203.0.113.255") == "203.0.113.xxx"

    def test_zero_last_octet(self):
        assert mask_ip_address("192.168.1.0") == "192.168.1.xxx"

    def test_all_zeros(self):
        assert mask_ip_address("0.0.0.0") == "0.0.0.xxx"

    def test_all_255(self):
        assert mask_ip_address("255.255.255.255") == "255.255.255.xxx"

    def test_deterministic_same_input_same_output(self):
        ip = "10.0.0.1"
        results = {mask_ip_address(ip) for _ in range(10)}
        assert len(results) == 1

    def test_strips_whitespace(self):
        assert mask_ip_address("  192.168.1.1  ") == "192.168.1.xxx"


class TestIPv6Masking:
    def test_full_form_eight_groups(self):
        result = mask_ip_address("2001:0db8:85a3:0000:0000:8a2e:0370:7334")
        assert result == "2001:0db8:85a3:0000:xxxx:xxxx:xxxx:xxxx"

    def test_all_zeros_ipv6(self):
        result = mask_ip_address("0000:0000:0000:0000:0000:0000:0000:0000")
        assert result == "0000:0000:0000:0000:xxxx:xxxx:xxxx:xxxx"

    def test_preserves_first_four_groups(self):
        result = mask_ip_address("fe80:abcd:1234:5678:aaaa:bbbb:cccc:dddd")
        assert result == "fe80:abcd:1234:5678:xxxx:xxxx:xxxx:xxxx"

    def test_shorthand_loopback_masked(self):
        assert mask_ip_address("::1") == "masked"

    def test_shorthand_with_double_colon_masked(self):
        assert mask_ip_address("2001:db8::1") == "masked"

    def test_shorthand_all_zeros_masked(self):
        assert mask_ip_address("::") == "masked"

    def test_deterministic_ipv6(self):
        ip = "2001:0db8:0000:0000:0000:0000:0000:0001"
        results = {mask_ip_address(ip) for _ in range(10)}
        assert len(results) == 1


class TestEdgeCases:
    def test_none_returns_unknown(self):
        assert mask_ip_address(None) == "unknown"

    def test_empty_string_returns_unknown(self):
        assert mask_ip_address("") == "unknown"

    def test_whitespace_only_returns_unknown(self):
        assert mask_ip_address("   ") == "unknown"

    def test_hostname_returns_masked(self):
        assert mask_ip_address("hostname.internal") == "masked"

    def test_malformed_ipv4_too_few_octets_returns_masked(self):
        assert mask_ip_address("192.168.1") == "masked"

    def test_malformed_ipv4_too_many_octets_returns_masked(self):
        assert mask_ip_address("192.168.1.1.1") == "masked"

    def test_malformed_ipv6_wrong_group_count_returns_masked(self):
        # Only 4 groups, not 8 — ambiguous but not shorthand (no '::')
        assert mask_ip_address("2001:db8:85a3:0000") == "masked"

    def test_non_string_returns_masked(self):
        assert mask_ip_address(12345) == "masked"  # type: ignore[arg-type]

    def test_random_garbage_returns_masked(self):
        assert mask_ip_address("not-an-ip-address") == "masked"
