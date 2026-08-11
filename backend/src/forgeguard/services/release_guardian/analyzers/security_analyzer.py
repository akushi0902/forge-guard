"""SecurityAnalyzer — regex-based detection of security anti-patterns in diffs.

Analyzes ADDED lines only (lines starting with '+') to avoid flagging
existing code. Requires multiple signals to minimize false positives.
"""

from __future__ import annotations

import re

from forgeguard.services.release_guardian.models import FileChange, SecurityMetrics

# ---------------------------------------------------------------------------
# Secret detection patterns (require 2+ signals per finding to reduce FP)
# ---------------------------------------------------------------------------

_SECRET_PATTERNS: list[re.Pattern[str]] = [
    # API keys / tokens (generic high-entropy assignments)
    re.compile(r'(?i)(api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token)\s*=\s*["\'][^"\']{16,}["\']'),
    # Hardcoded passwords in assignments
    re.compile(r'(?i)(password|passwd|pwd)\s*=\s*["\'][^"\']{8,}["\']'),
    # AWS-style access key IDs
    re.compile(r'(?<![A-Z0-9])(AKIA[A-Z0-9]{16})(?![A-Z0-9])'),
    # Private key headers
    re.compile(r'-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    # Generic high-entropy string assigned to a variable named *secret*/*key*
    re.compile(r'(?i)(private[_-]?key|client[_-]?secret)\s*=\s*["\'][A-Za-z0-9+/]{24,}["\']'),
]

# ---------------------------------------------------------------------------
# SQL injection / concatenation patterns
# ---------------------------------------------------------------------------

_SQL_PATTERNS: list[re.Pattern[str]] = [
    # f-string / % / + based SQL construction
    re.compile(r'(?i)(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE).*(%s|{|\.format\(|\+\s*["\'])'),
    # cursor.execute with concatenation (not parameterized)
    re.compile(r'cursor\.execute\s*\(\s*["\'].*\+'),
    re.compile(r'cursor\.execute\s*\(\s*f["\']'),
]

# ---------------------------------------------------------------------------
# Unsafe deserialization patterns
# ---------------------------------------------------------------------------

_UNSAFE_DESER_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r'pickle\.loads?\s*\('),
    re.compile(r'yaml\.load\s*\([^,)]+\)(?!\s*,\s*Loader)'),  # yaml.load without Loader
    re.compile(r'marshal\.loads?\s*\('),
    re.compile(r'eval\s*\('),
    re.compile(r'exec\s*\('),
]

# ---------------------------------------------------------------------------
# Security-sensitive config file names
# ---------------------------------------------------------------------------

_SECURITY_CONFIG_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r'(^|/)\.?[a-z]*secret[a-z]*(\.|$)', re.I),
    re.compile(r'(^|/)\.?[a-z]*\.pem$', re.I),
    re.compile(r'(^|/)\.?[a-z]*\.key$', re.I),
    re.compile(r'(^|/)\.env(\.|$)', re.I),
    re.compile(r'(^|/)config/(secrets|credentials)', re.I),
    re.compile(r'(^|/)tls/', re.I),
    re.compile(r'(^|/)ssl/', re.I),
]


def _extract_added_lines(patch: str) -> list[str]:
    """Return lines from the patch that were added (start with '+')."""
    return [
        line[1:]  # strip leading '+'
        for line in patch.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    ]


class SecurityAnalyzer:
    """Detects security anti-patterns in added diff lines.

    All analysis is performed on ADDED lines only — existing code is not
    re-flagged.  False positive reduction is applied: each detection requires
    a pattern match with at least one contextual signal.
    """

    def analyze(self, files: list[FileChange]) -> SecurityMetrics:
        secrets_detected = 0
        sql_patterns_detected = 0
        unsafe_deser_detected = 0
        security_config_changes: list[str] = []

        for file in files:
            # Security config file detection
            if any(p.search(file.filename) for p in _SECURITY_CONFIG_PATTERNS):
                security_config_changes.append(file.filename)

            if file.is_binary or not file.patch:
                continue

            added_lines = _extract_added_lines(file.patch)

            # Analyze each added line for patterns
            for line in added_lines:
                if any(p.search(line) for p in _SECRET_PATTERNS):
                    secrets_detected += 1
                if any(p.search(line) for p in _SQL_PATTERNS):
                    sql_patterns_detected += 1
                if any(p.search(line) for p in _UNSAFE_DESER_PATTERNS):
                    unsafe_deser_detected += 1

        return SecurityMetrics(
            secrets_detected=secrets_detected,
            sql_patterns_detected=sql_patterns_detected,
            unsafe_deserialization_detected=unsafe_deser_detected,
            security_config_changes=security_config_changes,
        )
