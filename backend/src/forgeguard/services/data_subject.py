"""DataSubjectService: GDPR Articles 15, 16, 17, 20 implementation.

Orchestrates all four data subject rights operations for authenticated users:
  - access_data()   — Article 15: right of access
  - rectify_data()  — Article 16: right to rectification
  - erase_data()    — Article 17: right to erasure
  - export_data()   — Article 20: right to data portability

Design:
  - Uses asyncpg pool directly for operations requiring explicit transaction
    control (e.g. SERIALIZABLE erasure) or cross-table raw SQL.
  - Erasure uses cryptographic overwrite of PII fields (not soft-delete),
    anonymizes audit_logs actor_id references, deactivates the account,
    and revokes all refresh tokens — atomically within a SERIALIZABLE tx.
  - The audit record for the erasure action is written BEFORE the actor_id
    anonymization so the original actor_id is recorded; the subsequent
    UPDATE excludes that specific record.
  - Audit log immutability trigger allows actor_id → ANONYMIZED_USER_UUID
    updates only (see migration e1f2a3b4c5d6).
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Optional

import asyncpg
import structlog

from forgeguard.core.constants import ANONYMIZED_USER_UUID
from forgeguard.core.exceptions import BadRequestError, ConflictError

if TYPE_CHECKING:
    from forgeguard.services.audit import AuditService

logger = structlog.get_logger(__name__)

# Maximum number of SERIALIZABLE retry attempts for the erasure transaction.
_ERASURE_MAX_RETRIES = 3


def _decode_name(raw: Any) -> Optional[str]:
    """Decode the name field from bytes or string storage."""
    if isinstance(raw, (bytes, memoryview)):
        return bytes(raw).decode("utf-8", errors="replace")
    if isinstance(raw, str):
        return raw
    return None


class DataSubjectService:
    """Orchestrates GDPR data subject rights operations.

    Args:
        pool:          asyncpg connection pool.
        audit_service: AuditService for writing compliance audit records.
    """

    def __init__(
        self,
        pool: asyncpg.Pool,
        audit_service: Optional["AuditService"] = None,
    ) -> None:
        self._pool = pool
        self._audit = audit_service

    # ------------------------------------------------------------------
    # Article 15 — Right of Access
    # ------------------------------------------------------------------

    async def access_data(self, user_id: uuid.UUID) -> dict[str, Any]:
        """Return all PII and a summary of related records for the given user.

        Args:
            user_id: Authenticated user's UUID.

        Returns:
            Dict with id, email, name, role, created_at, and related_records counts.

        Raises:
            BadRequestError: If the user record is not found.
        """
        async with self._pool.acquire() as conn:
            user = await conn.fetchrow(
                "SELECT id, email, name_encrypted, role, is_active, created_at "
                "FROM users WHERE id = $1 AND deleted_at IS NULL",
                user_id,
            )
            if user is None:
                raise BadRequestError("User not found.")

            audit_count: int = await conn.fetchval(
                "SELECT count(*) FROM audit_logs WHERE actor_id = $1",
                user_id,
            ) or 0

            assessments_count: int = await conn.fetchval(
                "SELECT count(*) FROM assessments WHERE requested_by = $1",
                user_id,
            ) or 0

            decisions_count: int = await conn.fetchval(
                "SELECT count(*) FROM release_decisions WHERE decided_by = $1",
                user_id,
            ) or 0

        name = _decode_name(user["name_encrypted"])

        logger.info(
            "gdpr.access_data",
            user_id=str(user_id),
            audit_count=audit_count,
            assessments_count=assessments_count,
            decisions_count=decisions_count,
        )

        if self._audit:
            try:
                await self._audit.log_event(
                    actor_id=user_id,
                    actor_role=user["role"],
                    action="gdpr.access_data",
                    resource_type="users",
                    resource_id=user_id,
                )
            except Exception as exc:
                logger.warning("gdpr.audit_write.failed", action="access_data", error=str(exc))

        return {
            "id": user["id"],
            "email": user["email"],
            "name": name,
            "role": user["role"],
            "created_at": user["created_at"],
            "related_records": {
                "audit_log_count": audit_count,
                "assessments_count": assessments_count,
                "decisions_count": decisions_count,
            },
        }

    # ------------------------------------------------------------------
    # Article 16 — Right to Rectification
    # ------------------------------------------------------------------

    async def rectify_data(
        self,
        user_id: uuid.UUID,
        role: str,
        *,
        email: Optional[str] = None,
        name: Optional[str] = None,
    ) -> dict[str, Any]:
        """Update the user's email and/or name.

        Args:
            user_id: Authenticated user's UUID.
            role:    User's current role (for audit record).
            email:   New email address (must be unique).
            name:    New display name.

        Returns:
            Updated user record dict (id, email, name, role, updated_at).

        Raises:
            BadRequestError: If neither email nor name is provided.
            ConflictError:   If the new email is already used by another account.
        """
        if email is None and name is None:
            raise BadRequestError("At least one field (email or name) must be provided.")

        async with self._pool.acquire() as conn:
            # Snapshot before-state for audit (mask PII).
            user = await conn.fetchrow(
                "SELECT id, email, name_encrypted, role, updated_at "
                "FROM users WHERE id = $1 AND deleted_at IS NULL",
                user_id,
            )
            if user is None:
                raise BadRequestError("User not found.")

            # Check email uniqueness before updating.
            if email is not None:
                existing = await conn.fetchrow(
                    "SELECT id FROM users WHERE email = $1 AND id != $2",
                    email,
                    user_id,
                )
                if existing is not None:
                    raise ConflictError("Email address is already in use by another account.")

            # Build SET clause from provided fields.
            set_parts: list[str] = ["updated_at = NOW()"]
            params: list[Any] = []
            idx = 1

            if email is not None:
                set_parts.append(f"email = ${idx}")
                params.append(email)
                idx += 1

            if name is not None:
                set_parts.append(f"name_encrypted = ${idx}")
                params.append(name.encode("utf-8"))
                idx += 1

            params.append(user_id)
            q = (
                f"UPDATE users SET {', '.join(set_parts)} "
                f"WHERE id = ${idx} AND deleted_at IS NULL "
                "RETURNING id, email, name_encrypted, role, updated_at"
            )
            updated = await conn.fetchrow(q, *params)

        if updated is None:
            raise BadRequestError("User not found.")

        name_decoded = _decode_name(updated["name_encrypted"])

        logger.info("gdpr.rectify_data", user_id=str(user_id))

        if self._audit:
            try:
                await self._audit.log_mutation(
                    actor_id=user_id,
                    actor_role=role,
                    action="gdpr.rectify_data",
                    resource_type="users",
                    resource_id=user_id,
                    before_state={
                        "email_domain": user["email"].split("@")[-1] if "@" in user["email"] else "[masked]",
                    },
                    after_state={
                        "email_domain": updated["email"].split("@")[-1] if "@" in updated["email"] else "[masked]",
                        "name_updated": name is not None,
                    },
                )
            except Exception as exc:
                logger.warning("gdpr.audit_write.failed", action="rectify_data", error=str(exc))

        return {
            "id": updated["id"],
            "email": updated["email"],
            "name": name_decoded,
            "role": updated["role"],
            "updated_at": updated["updated_at"],
        }

    # ------------------------------------------------------------------
    # Article 17 — Right to Erasure
    # ------------------------------------------------------------------

    async def erase_data(self, user_id: uuid.UUID, role: str) -> None:
        """Cryptographically erase a user's PII and anonymize audit references.

        Operation ordering (within a SERIALIZABLE transaction):
          1. Guard: if user is already erased, return 204 idempotently.
          2. Guard: block last-Platform-Admin erasure (409).
          3. Write the erasure audit record (original actor_id).
          4. Overwrite email and name_encrypted with random data.
          5. Set is_active=false, deleted_at=NOW().
          6. UPDATE audit_logs: actor_id → ANONYMIZED_USER_UUID, excluding
             the erasure record written in step 3.
          7. Revoke all refresh tokens for the user.

        Args:
            user_id: Authenticated user's UUID.
            role:    User's current role (for audit record and admin guard).

        Raises:
            ConflictError: If the user is the last active Platform Admin.
        """
        for attempt in range(_ERASURE_MAX_RETRIES):
            try:
                await self._erase_data_once(user_id, role)
                return
            except asyncpg.SerializationError:
                if attempt < _ERASURE_MAX_RETRIES - 1:
                    logger.warning(
                        "gdpr.erase_data.serialization_retry",
                        user_id=str(user_id),
                        attempt=attempt + 1,
                    )
                else:
                    logger.error(
                        "gdpr.erase_data.serialization_failed",
                        user_id=str(user_id),
                    )
                    raise

    async def _erase_data_once(self, user_id: uuid.UUID, role: str) -> None:
        """Single attempt at SERIALIZABLE erasure transaction."""
        async with self._pool.acquire() as conn:
            async with conn.transaction(isolation="serializable"):
                # 1. Idempotency: if already erased, return silently.
                user = await conn.fetchrow(
                    "SELECT id, email, role, is_active, deleted_at "
                    "FROM users WHERE id = $1",
                    user_id,
                )
                if user is None:
                    return  # Not found — already erased or never existed.
                if user["deleted_at"] is not None or not user["is_active"]:
                    logger.info("gdpr.erase_data.already_erased", user_id=str(user_id))
                    return

                # 2. Last Platform Admin guard.
                if user["role"] == "platform_admin":
                    admin_count: int = await conn.fetchval(
                        "SELECT count(*) FROM users "
                        "WHERE role = 'platform_admin' AND is_active = true "
                        "AND deleted_at IS NULL AND id != $1",
                        user_id,
                    ) or 0
                    if admin_count < 1:
                        raise ConflictError(
                            "Cannot erase the last active Platform Admin. "
                            "Assign the Platform Admin role to another user first."
                        )

                # 3. Write erasure audit record BEFORE anonymization.
                erasure_record_id: Optional[uuid.UUID] = None
                if self._audit:
                    try:
                        record = await self._audit.log_event(
                            actor_id=user_id,
                            actor_role=role,
                            action="gdpr.erase_data",
                            resource_type="users",
                            resource_id=user_id,
                            after_state={"status": "erased"},
                        )
                        erasure_record_id = record.get("id")
                    except Exception as exc:
                        logger.critical(
                            "gdpr.erase_data.audit_write_failed",
                            user_id=str(user_id),
                            error=str(exc),
                        )

                # 4. Cryptographically overwrite PII fields.
                random_email = f"[erased-{uuid.uuid4()}]@deleted.forgeguard.internal"
                random_name_bytes = os.urandom(32)
                await conn.execute(
                    "UPDATE users SET "
                    "  email = $1, "
                    "  name_encrypted = $2, "
                    "  is_active = false, "
                    "  deleted_at = NOW(), "
                    "  updated_at = NOW() "
                    "WHERE id = $3",
                    random_email,
                    random_name_bytes,
                    user_id,
                )

                # 5. Anonymize audit_logs actor references (excluding erasure record).
                anon_uuid = ANONYMIZED_USER_UUID
                if erasure_record_id is not None:
                    await conn.execute(
                        "UPDATE audit_logs SET actor_id = $1 "
                        "WHERE actor_id = $2 AND id != $3",
                        anon_uuid,
                        user_id,
                        erasure_record_id,
                    )
                else:
                    await conn.execute(
                        "UPDATE audit_logs SET actor_id = $1 "
                        "WHERE actor_id = $2",
                        anon_uuid,
                        user_id,
                    )

                # 6. Revoke all refresh tokens for this user.
                await conn.execute(
                    "UPDATE refresh_tokens SET revoked_at = NOW() "
                    "WHERE user_id = $1 AND revoked_at IS NULL",
                    user_id,
                )

        logger.info("gdpr.erase_data.complete", user_id=str(user_id))

    # ------------------------------------------------------------------
    # Article 20 — Right to Data Portability
    # ------------------------------------------------------------------

    async def export_data(self, user_id: uuid.UUID) -> dict[str, Any]:
        """Aggregate all user data into a portable JSON structure.

        Args:
            user_id: Authenticated user's UUID.

        Returns:
            Dict with profile, audit_logs, assessments, decisions arrays.

        Raises:
            BadRequestError: If the user record is not found.
        """
        async with self._pool.acquire() as conn:
            user = await conn.fetchrow(
                "SELECT id, email, name_encrypted, role, created_at, updated_at "
                "FROM users WHERE id = $1 AND deleted_at IS NULL",
                user_id,
            )
            if user is None:
                raise BadRequestError("User not found.")

            audit_rows = await conn.fetch(
                "SELECT id, action, resource_type, resource_id, "
                "       after_state, ip_address_masked, correlation_id, created_at "
                "FROM audit_logs WHERE actor_id = $1 "
                "ORDER BY created_at DESC",
                user_id,
            )

            assessment_rows = await conn.fetch(
                "SELECT id, service_id, overall_score, health_score, risk_score, "
                "       commit_sha, status, created_at "
                "FROM assessments WHERE requested_by = $1 "
                "ORDER BY created_at DESC",
                user_id,
            )

            decision_rows = await conn.fetch(
                "SELECT id, assessment_id, outcome, rationale, comment, "
                "       conditions, created_at "
                "FROM release_decisions WHERE decided_by = $1 "
                "ORDER BY created_at DESC",
                user_id,
            )

        name = _decode_name(user["name_encrypted"])

        def _row_to_dict(row: asyncpg.Record) -> dict[str, Any]:
            d: dict[str, Any] = {}
            for k in row.keys():
                v = row[k]
                if isinstance(v, uuid.UUID):
                    d[k] = str(v)
                elif isinstance(v, datetime):
                    d[k] = v.isoformat()
                elif isinstance(v, (bytes, memoryview)):
                    d[k] = "[binary data]"
                else:
                    d[k] = v
            return d

        logger.info(
            "gdpr.export_data",
            user_id=str(user_id),
            audit_count=len(audit_rows),
            assessment_count=len(assessment_rows),
            decision_count=len(decision_rows),
        )

        if self._audit:
            try:
                await self._audit.log_event(
                    actor_id=user_id,
                    actor_role=user["role"],
                    action="gdpr.export_data",
                    resource_type="users",
                    resource_id=user_id,
                )
            except Exception as exc:
                logger.warning("gdpr.audit_write.failed", action="export_data", error=str(exc))

        return {
            "profile": {
                "id": str(user["id"]),
                "email": user["email"],
                "name": name,
                "role": user["role"],
                "created_at": user["created_at"].isoformat() if isinstance(user["created_at"], datetime) else str(user["created_at"]),
            },
            "audit_logs": [_row_to_dict(r) for r in audit_rows],
            "assessments": [_row_to_dict(r) for r in assessment_rows],
            "decisions": [_row_to_dict(r) for r in decision_rows],
        }
