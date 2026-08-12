"""IP address masking utilities for audit and GDPR compliance (WO-029).

Masking strategy:
    IPv4: replace the last **two** octets with 'xxx'.
          ``192.168.1.100`` → ``192.168.xxx.xxx``
    IPv6: replace the last **5 groups** (80 bits) with 'xxxx'.
          ``2001:db8:85a3:0000:0000:8a2e:0370:7334``
          → ``2001:db8:85a3:xxxx:xxxx:xxxx:xxxx:xxxx``
    IPv6 shorthand (contains '::'): return 'masked' (ambiguous group count).
    Missing / empty input: return 'unknown'.
    Unrecognised format: return 'masked'.

This module follows WO-029's masking spec (2 IPv4 octets preserved).
``forgeguard.core.ip_masking`` preserves 3 octets and is used by the audit
pre-hook middleware (WO-019) — the two modules serve different purposes.
"""

from __future__ import annotations

import re

_IPV4_RE = re.compile(
    r"^(\d{1,3})\.(\d{1,3})\.\d{1,3}\.\d{1,3}$"
)


def mask_ip_address(ip: str | None) -> str:
    """Mask an IP address before audit log storage.

    Args:
        ip: Raw IP address string, or ``None``.

    Returns:
        Masked IP string.

    Examples::

        mask_ip_address("192.168.1.100")   # → "192.168.xxx.xxx"
        mask_ip_address("10.0.0.1")        # → "10.0.xxx.xxx"
        mask_ip_address("")                # → "unknown"
        mask_ip_address(None)              # → "unknown"
        mask_ip_address("garbage")         # → "masked"
        mask_ip_address("2001:db8:85a3:0000:0000:8a2e:0370:7334")
        # → "2001:db8:85a3:xxxx:xxxx:xxxx:xxxx:xxxx"
    """
    if not ip:
        return "unknown"

    if not isinstance(ip, str):
        return "masked"

    stripped = ip.strip()
    if not stripped:
        return "unknown"

    # ---- IPv4 -----------------------------------------------------------
    m = _IPV4_RE.match(stripped)
    if m:
        return f"{m.group(1)}.{m.group(2)}.xxx.xxx"

    # ---- IPv6 -----------------------------------------------------------
    if ":" in stripped:
        if "::" in stripped:
            # Shorthand / compressed notation: ambiguous, fully mask.
            return "masked"

        groups = stripped.split(":")
        if len(groups) == 8:
            # Keep first 3 groups; mask last 5 (80 bits).
            masked = groups[:3] + ["xxxx"] * 5
            return ":".join(masked)

        return "masked"

    return "masked"
