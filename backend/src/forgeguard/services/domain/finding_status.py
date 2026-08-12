"""Finding status lifecycle domain types (WO-041).

Defines the valid statuses for a Finding and the allowed state-machine
transitions enforced by FindingRepository.update_status.

Lifecycle:
    open -> acknowledged (developer acknowledges the violation)
    open -> exception_granted (waiver approved for known risk)
    acknowledged -> remediated (fix deployed and verified)
    remediated -> reopened (re-evaluation finds the violation again)
    exception_granted -> reopened (exception expired or revoked)
    reopened -> acknowledged (developer re-acknowledges after reopen)
    reopened -> exception_granted (new exception granted after reopen)
"""

from __future__ import annotations

from enum import Enum


class FindingStatus(str, Enum):
    """Valid lifecycle states for a Finding record.

    Inherits from str so values compare equal to their string literals,
    making asyncpg query parameters, JSON serialisation, and CHECK
    constraints work without explicit .value access.
    """

    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    REMEDIATED = "remediated"
    EXCEPTION_GRANTED = "exception_granted"
    REOPENED = "reopened"


VALID_TRANSITIONS: dict[FindingStatus, frozenset[FindingStatus]] = {
    FindingStatus.OPEN: frozenset({
        FindingStatus.ACKNOWLEDGED,
        FindingStatus.EXCEPTION_GRANTED,
    }),
    FindingStatus.ACKNOWLEDGED: frozenset({
        FindingStatus.REMEDIATED,
    }),
    FindingStatus.REMEDIATED: frozenset({
        FindingStatus.REOPENED,
    }),
    FindingStatus.EXCEPTION_GRANTED: frozenset({
        FindingStatus.REOPENED,
    }),
    FindingStatus.REOPENED: frozenset({
        FindingStatus.ACKNOWLEDGED,
        FindingStatus.EXCEPTION_GRANTED,
    }),
}
