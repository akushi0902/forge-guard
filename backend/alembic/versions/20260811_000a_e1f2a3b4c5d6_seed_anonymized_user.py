"""Seed anonymized system user and extend audit immutability for GDPR erasure.

Revision ID: e1f2a3b4c5d6
Revises:     d0e1f2a3b4c5 (refresh_token_rotation)
Create Date: 2026-08-11 00:10:00 UTC

Changes:
  1. Extend users.role CHECK constraint to include 'system' role so the
     anonymized placeholder account has a distinct, non-persona role.
  2. Modify the audit immutability trigger to permit GDPR actor_id
     anonymization: allows UPDATE where ONLY actor_id changes to the
     well-known ANONYMIZED_USER_UUID (00000000-0000-0000-0000-000000000000).
     All other columns, all DELETEs, and any other UPDATE remain blocked.
  3. Insert the well-known anonymized user record into the users table.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "e1f2a3b4c5d6"
down_revision: str = "d0e1f2a3b4c5"
branch_labels = None
depends_on = None

_ANONYMIZED_USER_UUID = "00000000-0000-0000-0000-000000000000"
_ANONYMIZED_USER_EMAIL = "[anonymized]@system.internal"

# bcrypt hashes are ALWAYS exactly 60 chars: "$2b$12$" (7) + 22-char salt +
# 31-char digest. This placeholder is a structurally valid, 60-char bcrypt
# string that no password will ever verify against, so the anonymized/system
# account can never authenticate. Do NOT lengthen it — password_hash is
# VARCHAR(60) and the old placeholder was 65 chars, causing
# StringDataRightTruncationError.
_ANONYMIZED_USER_PASSWORD_HASH = (
    "$2b$12$AnonymizedUserCannotLoginPlaceholderHash0000000000000"
)


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Extend the users.role CHECK constraint to include 'system'.
    # ------------------------------------------------------------------
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS valid_role")
    op.execute(
        "ALTER TABLE users ADD CONSTRAINT valid_role CHECK ("
        "role IN ("
        "'developer','tech_lead','security_reviewer',"
        "'platform_admin','engineering_manager','operator','system'"
        "))"
    )

    # ------------------------------------------------------------------
    # 2. Replace the audit immutability trigger function to permit GDPR
    #    actor_id anonymization (actor_id → ANONYMIZED_USER_UUID only).
    # ------------------------------------------------------------------
    op.execute("""
        CREATE OR REPLACE FUNCTION prevent_audit_modification()
        RETURNS TRIGGER
        LANGUAGE plpgsql
        AS $$
        DECLARE
            _anon_uuid UUID := '00000000-0000-0000-0000-000000000000';
        BEGIN
            -- Allow actor_id anonymization for GDPR erasure.
            -- Only permit an UPDATE where the new actor_id is the anonymized
            -- UUID and every other column is unchanged.
            IF TG_OP = 'UPDATE'
               AND NEW.actor_id = _anon_uuid
               AND NEW.action IS NOT DISTINCT FROM OLD.action
               AND NEW.actor_role IS NOT DISTINCT FROM OLD.actor_role
               AND NEW.resource_type IS NOT DISTINCT FROM OLD.resource_type
               AND NEW.resource_id IS NOT DISTINCT FROM OLD.resource_id
               AND NEW.before_state IS NOT DISTINCT FROM OLD.before_state
               AND NEW.after_state IS NOT DISTINCT FROM OLD.after_state
               AND NEW.ip_address_masked IS NOT DISTINCT FROM OLD.ip_address_masked
               AND NEW.correlation_id IS NOT DISTINCT FROM OLD.correlation_id
               AND NEW.created_at IS NOT DISTINCT FROM OLD.created_at
            THEN
                RETURN NEW;
            END IF;

            RAISE EXCEPTION
                'Audit records are immutable — UPDATE and DELETE are not permitted '
                'on the audit_logs table. Attempted operation: %', TG_OP;
            RETURN NULL;
        END;
        $$
    """)

    # ------------------------------------------------------------------
    # 3. Seed the anonymized user.
    # ------------------------------------------------------------------
    op.execute(f"""
        INSERT INTO users (
            id, email, name_encrypted, password_hash, role,
            is_active, failed_login_attempts, locked_until,
            deleted_at, created_at, updated_at
        )
        VALUES (
            '{_ANONYMIZED_USER_UUID}',
            '{_ANONYMIZED_USER_EMAIL}',
            '[Anonymized User]'::bytea,
            '{_ANONYMIZED_USER_PASSWORD_HASH}',
            'system',
            false,
            0,
            NULL,
            NULL,
            NOW(),
            NOW()
        )
        ON CONFLICT (id) DO NOTHING
    """)


def downgrade() -> None:
    # Remove the anonymized user.
    op.execute(
        f"DELETE FROM users WHERE id = '{_ANONYMIZED_USER_UUID}'"
    )

    # Revert the role CHECK constraint (remove 'system').
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS valid_role")
    op.execute(
        "ALTER TABLE users ADD CONSTRAINT valid_role CHECK ("
        "role IN ("
        "'developer','tech_lead','security_reviewer',"
        "'platform_admin','engineering_manager','operator'"
        "))"
    )

    # Revert the trigger to the strict immutable version.
    op.execute("""
        CREATE OR REPLACE FUNCTION prevent_audit_modification()
        RETURNS TRIGGER
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION
                'Audit records are immutable — UPDATE and DELETE are not permitted '
                'on the audit_logs table. Attempted operation: %', TG_OP;
            RETURN NULL;
        END;
        $$
    """)
