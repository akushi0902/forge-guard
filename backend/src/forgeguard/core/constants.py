"""Application-level constants shared across the ForgeGuard codebase.

Centralising constants here prevents magic values from being scattered
across modules and makes them easy to audit.
"""

from __future__ import annotations

import uuid

# ---------------------------------------------------------------------------
# GDPR / Data Subject Rights
# ---------------------------------------------------------------------------

#: Well-known UUID used as the actor_id for anonymized audit log entries.
#: When a user exercises their right to erasure (GDPR Article 17), their
#: actor_id in existing audit_logs is replaced with this UUID to preserve
#: the audit trail structure while removing the PII linkage.
#: This UUID must be seeded in the users table by migration 000a.
ANONYMIZED_USER_UUID: uuid.UUID = uuid.UUID("00000000-0000-0000-0000-000000000000")

#: Email address stored for the anonymized system user account.
ANONYMIZED_USER_EMAIL: str = "[anonymized]@system.internal"

#: Role assigned to the anonymized system user (added to users.role CHECK).
ANONYMIZED_USER_ROLE: str = "system"
