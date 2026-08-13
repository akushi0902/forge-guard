"""Audit-specific IP address masking for GDPR compliance.

Masking rules (per WO-019):
  - IPv4: replace last octet with 'xxx'.
    ``192.168.1.100`` → ``192.168.1.xxx``
  - IPv6 full form (8 groups): replace last 4 groups with 'xxxx'.
    ``2001:db8:85a3:0:0:8a2e:370:7334`` → ``2001:db8:85a3:0:xxxx:xxxx:xxxx:xxxx``
  - IPv6 shorthand (contains '::'): ambiguous group count, return 'masked'.
  - Missing input (None, empty string): return 'unknown'.
  - Unrecognised format: return 'masked'.

This module is distinct from ``forgeguard.utils.pii_masking.mask_ip``, which
is used by the structured log pipeline and preserves the first *two* octets.
The audit context masking is more conservative (preserves 3 octets) and uses
a different sentinel vocabulary ('xxx'/'xxxx' vs '***') so consumers can
distinguish the two masking layers in log analysis.
"""

from __future__ import annotations

import re

_IPV4_EXACT_RE = re.compile(
    r"^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.\d{1,3}$"
)


def mask_ip_address(ip: str | None) -> str:
    """Mask an IP address for storage in the audit context.

    Args:
        ip: Raw IP address string (IPv4 or IPv6).

    Returns:
        Masked IP string.  Returns ``'unknown'`` for ``None`` or empty input,
        ``'masked'`` for unrecognised / ambiguous formats.

    Examples::

        mask_ip_address("192.168.1.100")
        # → "192.168.1.xxx"

        mask_ip_address("2001:0db8:85a3:0000:0000:8a2e:0370:7334")
        # → "2001:0db8:85a3:0000:xxxx:xxxx:xxxx:xxxx"

        mask_ip_address("")      # → "unknown"
        mask_ip_address(None)    # → "unknown"
        mask_ip_address("bad")   # → "masked"
    """
    if not ip:
        return "unknown"

    if not isinstance(ip, str):
        return "masked"

    stripped = ip.strip()
    if not stripped:
        return "unknown"

    # ---- IPv4 -----------------------------------------------------------
    m = _IPV4_EXACT_RE.match(stripped)
    if m:
        return f"{m.group(1)}.{m.group(2)}.{m.group(3)}.xxx"

    # ---- IPv6 -----------------------------------------------------------
    if ":" in stripped:
        # Shorthand notation (contains '::') is ambiguous — fully mask.
        if "::" in stripped:
            return "masked"

        groups = stripped.split(":")
        if len(groups) == 8:
            masked = groups[:4] + ["xxxx"] * 4
            return ":".join(masked)

        return "masked"

    # ---- Unrecognised ---------------------------------------------------
    return "masked"
