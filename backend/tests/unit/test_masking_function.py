"""Unit tests for the PII masking function contract (WO-100).

Focuses on the deterministic input/output pairs specified in the acceptance
criteria and compliance spec, Faker-generated realistic PII, and edge cases
mandated by the WO (None/empty, boundary IPs, look-alike strings).

These tests complement the broader test_pii_masking.py with a compact,
parametrized-only surface that serves as runnable compliance evidence for
the GDPR/CCPA masking contract.

Run with::

    pytest tests/unit/test_masking_function.py -v
"""

from __future__ import annotations

import re

import pytest

try:
    from faker import Faker

    _FAKER_AVAILABLE = True
    _faker = Faker()
except ImportError:
    _FAKER_AVAILABLE = False
    _faker = None  # type: ignore[assignment]

from forgeguard.utils.pii_masking import mask_email, mask_ip, mask_name

# ---------------------------------------------------------------------------
# Regex patterns for "is the output properly masked?"
# ---------------------------------------------------------------------------

# An unmasked email STILL contains raw characters before @.
# A masked email must match: single_char + *** + @domain
_MASKED_EMAIL_RE = re.compile(r"^.{1}\*{3}@.+$")

# Masked name words: first char + ***
_MASKED_NAME_WORD_RE = re.compile(r"^.\*{3}$")

# Masked IPv4: first two octets + ***.***
_MASKED_IPV4_RE = re.compile(r"^\d{1,3}\.\d{1,3}\.\*{3}\.\*{3}$")

# Raw email detector (should NOT appear in masked output for multi-char local parts)
_RAW_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]{2,}@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


# ---------------------------------------------------------------------------
# mask_email — parametrized exact input/output pairs (from WO spec)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    # WO spec canonical cases
    ("john.doe@example.com",        "j***@example.com"),
    ("alice@corp.example.co.uk",    "a***@corp.example.co.uk"),
    # Single-char local
    ("a@b.io",                      "a***@b.io"),
    # Plus addressing (tag stripped in local, first char preserved)
    ("user+tag@sub.domain.com",     "u***@sub.domain.com"),
    # Mixed case
    ("Admin@Company.COM",           "A***@Company.COM"),
    # Numeric start
    ("123user@example.com",         "1***@example.com"),
    # Unicode local part
    ("üser@example.com",            "ü***@example.com"),
])
def test_mask_email_exact_pairs(raw: str, expected: str) -> None:
    assert mask_email(raw) == expected


@pytest.mark.parametrize("raw", [
    None,
    "",
])
def test_mask_email_null_and_empty(raw: str | None) -> None:
    result = mask_email(raw)
    # None in → None out; empty in → empty out
    assert result == raw


def test_mask_email_no_at_sign_returns_masked() -> None:
    assert mask_email("not-an-email") == "[MASKED]"


def test_mask_email_multiple_at_signs_uses_first() -> None:
    # "a@b@c.com" → local="a", domain="b@c.com"
    result = mask_email("a@b@c.com")
    assert result is not None
    assert result.startswith("a***@")


@pytest.mark.parametrize("lookalike", [
    "not@",          # no domain
    "@example.com",  # no local
])
def test_mask_email_degenerate_forms_are_safe(lookalike: str) -> None:
    result = mask_email(lookalike)
    assert result is not None


@pytest.mark.skipif(not _FAKER_AVAILABLE, reason="faker not installed")
def test_mask_email_faker_emails_are_masked() -> None:
    """Faker-generated email addresses must all be masked correctly."""
    for _ in range(20):
        email = _faker.email()
        result = mask_email(email)
        assert result is not None
        assert "@" in result
        local_raw = email.split("@")[0]
        if len(local_raw) > 1:
            # Multi-char local: should NOT appear verbatim after masking
            assert result != email, f"email {email!r} was not masked"
            assert "***" in result


# ---------------------------------------------------------------------------
# mask_name — parametrized exact input/output pairs (from WO spec)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    # WO spec canonical case
    ("John Doe",       "J*** D***"),
    # Single name
    ("Alice",          "A***"),
    # Three-part name
    ("Mary Jane Watson", "M*** J*** W***"),
    # Single character — unchanged
    ("J",              "J"),
    # Lowercase
    ("alice bob",      "a*** b***"),
    # Unicode
    ("José García",    "J*** G***"),
    ("Ångström Björk", "Å*** B***"),
])
def test_mask_name_exact_pairs(raw: str, expected: str) -> None:
    assert mask_name(raw) == expected


@pytest.mark.parametrize("raw", [
    None,
    "",
])
def test_mask_name_null_and_empty(raw: str | None) -> None:
    result = mask_name(raw)
    assert result == raw


@pytest.mark.skipif(not _FAKER_AVAILABLE, reason="faker not installed")
def test_mask_name_faker_names_are_masked() -> None:
    """Faker-generated names must have each word masked."""
    for _ in range(20):
        name = _faker.name()
        result = mask_name(name)
        assert result is not None
        parts = result.split()
        for part in parts:
            # Each word must either be a single char or end with ***
            assert len(part) == 1 or part.endswith("***"), (
                f"word {part!r} in masked name {result!r} is not properly masked"
            )


# ---------------------------------------------------------------------------
# mask_ip — parametrized exact input/output pairs (from WO spec)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    # WO spec canonical case
    ("192.168.1.100",  "192.168.***.***"),
    # Private ranges
    ("10.0.0.1",       "10.0.***.***"),
    ("172.16.0.1",     "172.16.***.***"),
    # Loopback
    ("127.0.0.1",      "127.0.***.***"),
    # Boundary values
    ("0.0.0.0",        "0.0.***.***"),
    ("255.255.255.255", "255.255.***.***"),
    # Public address
    ("203.0.113.42",   "203.0.***.***"),
])
def test_mask_ip_exact_pairs(raw: str, expected: str) -> None:
    assert mask_ip(raw) == expected


def test_mask_ip_ipv6_shorthand_fully_masked() -> None:
    assert mask_ip("::1") == "[MASKED_IP]"


def test_mask_ip_ipv6_fe80_fully_masked() -> None:
    assert mask_ip("fe80::1") == "[MASKED_IP]"


def test_mask_ip_ipv6_full_form_preserves_first_two_groups() -> None:
    result = mask_ip("2001:0db8:0000:0000:0000:0000:0000:0001")
    assert result is not None
    assert result.startswith("2001:0db8:")
    assert "*" in result


@pytest.mark.parametrize("raw", [
    None,
    "",
])
def test_mask_ip_null_and_empty(raw: str | None) -> None:
    result = mask_ip(raw)
    assert result == raw


def test_mask_ip_hostname_is_masked() -> None:
    assert mask_ip("hostname.internal") == "[MASKED_IP]"


def test_mask_ip_garbage_is_masked() -> None:
    assert mask_ip("not-an-ip") == "[MASKED_IP]"


@pytest.mark.skipif(not _FAKER_AVAILABLE, reason="faker not installed")
def test_mask_ip_faker_ipv4_addresses_are_masked() -> None:
    """Faker-generated IPv4 addresses must match the masked pattern."""
    for _ in range(20):
        ip = _faker.ipv4()
        result = mask_ip(ip)
        assert result is not None
        assert _MASKED_IPV4_RE.match(result), (
            f"IP {ip!r} masked to {result!r} does not match expected pattern"
        )


# ---------------------------------------------------------------------------
# Determinism — same input must always produce same output
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("email", [
    "john.doe@example.com",
    "alice@corp.example.co.uk",
    "user+tag@sub.domain.com",
])
def test_mask_email_is_deterministic(email: str) -> None:
    assert mask_email(email) == mask_email(email)


@pytest.mark.parametrize("name", [
    "John Doe",
    "Alice",
    "Mary Jane Watson",
    "José García",
])
def test_mask_name_is_deterministic(name: str) -> None:
    assert mask_name(name) == mask_name(name)


@pytest.mark.parametrize("ip", [
    "192.168.1.100",
    "10.0.0.1",
    "255.255.255.255",
    "0.0.0.0",
])
def test_mask_ip_is_deterministic(ip: str) -> None:
    assert mask_ip(ip) == mask_ip(ip)


# ---------------------------------------------------------------------------
# No raw PII in output — scan masked result for original value
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("email", [
    "john.doe@example.com",
    "alice@example.com",
    "admin@corp.internal",
])
def test_masked_email_does_not_contain_raw_local(email: str) -> None:
    local = email.split("@")[0]
    if len(local) > 1:
        result = mask_email(email) or ""
        # The raw local part (except first char) must not appear
        assert local[1:] not in result, (
            f"Raw local part {local[1:]!r} leaked in masked email {result!r}"
        )


@pytest.mark.parametrize("name,raw_parts", [
    ("John Doe",   ["ohn", "oe"]),
    ("Alice",      ["lice"]),
])
def test_masked_name_does_not_contain_raw_suffixes(
    name: str, raw_parts: list[str]
) -> None:
    result = mask_name(name) or ""
    for part in raw_parts:
        assert part not in result, (
            f"Raw name fragment {part!r} leaked in masked name {result!r}"
        )


@pytest.mark.parametrize("ip", [
    "192.168.1.100",
    "10.20.30.40",
])
def test_masked_ipv4_does_not_contain_last_two_octets(ip: str) -> None:
    octets = ip.split(".")
    result = mask_ip(ip) or ""
    # Third and fourth octets must not appear as digits in the result
    assert octets[2] not in result.replace("***", ""), (
        f"Third octet {octets[2]!r} leaked in masked IP {result!r}"
    )
    assert octets[3] not in result.replace("***", ""), (
        f"Fourth octet {octets[3]!r} leaked in masked IP {result!r}"
    )
