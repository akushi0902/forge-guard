"""Deterministic PII masking utility functions.

These pure functions mask Personally Identifiable Information before it can
appear in logs, audit records, or API responses.  Masking is deterministic —
the same input always produces the same masked output — enabling correlation
across masked log entries without exposing raw PII.

Contract:
  - Deterministic: same input → same output.
  - Never raises: malformed or unexpected input returns a safe placeholder.
  - Standalone: no database, HTTP, or external service dependencies.

Masking patterns:
  - Email: ``john.doe@example.com`` → ``j***@example.com``
  - Name:  ``John Doe``             → ``J*** D***``
  - IPv4:  ``192.168.1.100``        → ``192.168.***.***``
  - IPv6:  ``2001:db8::1``          → ``[MASKED_IP]`` (shorthand forms)
           ``2001:db8:0:0:0:0:0:1`` → ``2001:db8:*:*:*:*:*:*``
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# IPv4 pattern — full dotted-decimal with word boundaries
# ---------------------------------------------------------------------------

_IPV4_EXACT_RE = re.compile(
    r"^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$"
)

# ---------------------------------------------------------------------------
# Known PII field names and their masking category
# ---------------------------------------------------------------------------

#: Public frozenset of field names treated as PII regardless of value format.
PII_FIELD_NAMES: frozenset[str] = frozenset(
    {
        "email",
        "user_email",
        "actor_email",
        "name",
        "full_name",
        "first_name",
        "last_name",
        "display_name",
        "username",
        "ip_address",
        "remote_addr",
        "client_ip",
        "x_forwarded_for",
    }
)

_FIELD_TO_MASKER: dict[str, str] = {
    "email": "email",
    "user_email": "email",
    "actor_email": "email",
    "name": "name",
    "full_name": "name",
    "first_name": "name",
    "last_name": "name",
    "display_name": "name",
    "username": "name",
    "ip_address": "ip",
    "remote_addr": "ip",
    "client_ip": "ip",
    "x_forwarded_for": "ip",
}


# ---------------------------------------------------------------------------
# Public masking functions
# ---------------------------------------------------------------------------

def mask_email(email: str | None) -> str | None:
    """Mask an email address, preserving the first character and full domain.

    The local part (before ``@``) is replaced with ``<first_char>***``.
    The domain (after ``@``) is preserved verbatim.

    Args:
        email: Raw email address string.

    Returns:
        Masked email, e.g. ``j***@example.com``.
        Returns ``None`` for ``None`` input, ``""`` for empty string,
        ``"[MASKED]"`` for strings without an ``@`` sign.

    Examples::

        mask_email("john.doe@example.com")  → "j***@example.com"
        mask_email("a@example.com")         → "a***@example.com"
        mask_email("not-an-email")          → "[MASKED]"
        mask_email("")                      → ""
        mask_email(None)                    → None
    """
    if email is None:
        return None
    if not isinstance(email, str):
        return "[MASKED]"
    if not email:
        return email

    at_idx = email.find("@")
    if at_idx == -1:
        return "[MASKED]"

    local = email[:at_idx]
    domain = email[at_idx + 1:]

    if not local:
        masked_local = "***"
    else:
        masked_local = local[0] + "***"

    return f"{masked_local}@{domain}"


def mask_name(name: str | None) -> str | None:
    """Mask a name, preserving the first character of each whitespace-separated word.

    Each word is replaced with ``<first_char>***``.  Single-character words
    are returned unchanged.

    Args:
        name: Raw name string (may be first name, last name, or full name).

    Returns:
        Masked name, e.g. ``J*** D***``.
        Returns ``None`` for ``None`` input, ``""`` for empty string.

    Examples::

        mask_name("John Doe")  → "J*** D***"
        mask_name("Alice")     → "A***"
        mask_name("J")         → "J"
        mask_name("")          → ""
        mask_name(None)        → None
    """
    if name is None:
        return None
    if not isinstance(name, str):
        return "[MASKED]"
    if not name.strip():
        return name

    parts = name.split()
    masked_parts = [
        (word[0] + "***" if len(word) > 1 else word) for word in parts
    ]
    return " ".join(masked_parts)


def mask_ip(ip: str | None) -> str | None:
    """Mask an IP address, preserving the first two octets or groups.

    IPv4: the first two octets are preserved; the last two are replaced with
    ``***``.  For example: ``192.168.1.100`` → ``192.168.***.***``.

    IPv6 full form (8 groups): the first two groups are preserved; the
    remaining six are replaced with ``*``.

    IPv6 shorthand form (containing ``::``): fully masked to ``[MASKED_IP]``
    because the number of elided groups is ambiguous.

    Unrecognized format (hostnames, etc.): returns ``[MASKED_IP]``.

    Args:
        ip: Raw IP address string.

    Returns:
        Masked IP string, or ``[MASKED_IP]`` for unrecognized formats.
        Returns ``None`` for ``None`` input, ``""`` for empty string.

    Examples::

        mask_ip("192.168.1.100")                   → "192.168.***.***"
        mask_ip("10.0.0.1")                        → "10.0.***.***"
        mask_ip("2001:0db8:0000:0000:0000:0000:0000:0001")
                                                   → "2001:0db8:*:*:*:*:*:*"
        mask_ip("::1")                             → "[MASKED_IP]"
        mask_ip("hostname.internal")               → "[MASKED_IP]"
    """
    if ip is None:
        return None
    if not isinstance(ip, str):
        return "[MASKED_IP]"
    if not ip:
        return ip

    stripped = ip.strip()

    # ---- IPv4 -------------------------------------------------------
    m = _IPV4_EXACT_RE.match(stripped)
    if m:
        return f"{m.group(1)}.{m.group(2)}.***.***"

    # ---- IPv6 -------------------------------------------------------
    if ":" in stripped:
        # Shorthand notation (contains "::") is ambiguous — fully mask.
        if "::" in stripped:
            return "[MASKED_IP]"

        groups = stripped.split(":")
        if len(groups) >= 2:
            return f"{groups[0]}:{groups[1]}:*:*:*:*:*:*"

        return "[MASKED_IP]"

    # ---- Unrecognized -----------------------------------------------
    return "[MASKED_IP]"


def mask_field(field_name: str, value: str | None) -> str | None:
    """Dispatch to the appropriate masking function based on the field name.

    Known PII field names (``email``, ``name``, ``ip_address``, etc.) are
    routed to their dedicated masking function.  Unknown field names are
    returned unchanged.

    Args:
        field_name: The name of the field (case-insensitive lookup).
        value:      The field value to mask.

    Returns:
        Masked value, unchanged value for unknown fields, or ``None`` / ``""``
        for null / empty input.

    Examples::

        mask_field("email",      "user@example.com") → "u***@example.com"
        mask_field("name",       "John Doe")          → "J*** D***"
        mask_field("ip_address", "10.0.0.1")          → "10.0.***.***"
        mask_field("other",      "any value")          → "any value"
    """
    if value is None:
        return None

    masker = _FIELD_TO_MASKER.get(field_name.lower())
    if masker == "email":
        return mask_email(value)
    if masker == "name":
        return mask_name(value)
    if masker == "ip":
        return mask_ip(value)
    return value
