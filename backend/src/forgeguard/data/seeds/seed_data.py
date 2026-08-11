"""ForgeGuard demo seed data script.

Inserts a complete demo dataset into the database. Safe to re-run — all
inserts use ON CONFLICT DO NOTHING (idempotent by stable UUIDs / unique keys).

Usage:
    # Via asyncpg DSN:
    python -m forgeguard.data.seeds.seed_data postgresql://user:pass@host/db

    # Via environment variable:
    DATABASE_URL=postgresql+asyncpg://... python -m forgeguard.data.seeds.seed_data

Insert order respects FK dependencies:
    roles → permissions → users → role_permissions →
    services → policies → policy_rules →
    assessments → assessment_scores → findings →
    release_assessments → release_decisions →
    remediation_recommendations → exceptions →
    audit_logs (seed operation record)
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import asyncpg

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Summary tracking
# ---------------------------------------------------------------------------

@dataclass
class SeedSummary:
    inserted: dict[str, int] = field(default_factory=dict)
    skipped: dict[str, int] = field(default_factory=dict)
    failed: dict[str, int] = field(default_factory=dict)

    def record(self, table: str, status: str, count: int = 1) -> None:
        target = getattr(self, status)
        target[table] = target.get(table, 0) + count

    def log(self) -> None:
        total_in = sum(self.inserted.values())
        total_sk = sum(self.skipped.values())
        total_fa = sum(self.failed.values())
        logger.info(
            "Seed complete: %d inserted, %d skipped (already existed), %d failed",
            total_in, total_sk, total_fa,
        )
        for table in sorted(set(list(self.inserted) + list(self.skipped))):
            ins = self.inserted.get(table, 0)
            skp = self.skipped.get(table, 0)
            if ins or skp:
                logger.info("  %-40s inserted=%-4d skipped=%d", table, ins, skp)


# ---------------------------------------------------------------------------
# Low-level insert helper
# ---------------------------------------------------------------------------

async def _upsert_none(
    conn: asyncpg.Connection,
    table: str,
    rows: list[dict[str, Any]],
    conflict_col: str,
    summary: SeedSummary,
) -> None:
    """INSERT rows INTO table ON CONFLICT (conflict_col) DO NOTHING."""
    for row in rows:
        cols = list(row.keys())
        placeholders = ", ".join(f"${i + 1}" for i in range(len(cols)))
        col_names = ", ".join(cols)
        q = (
            f"INSERT INTO {table} ({col_names}) VALUES ({placeholders}) "
            f"ON CONFLICT ({conflict_col}) DO NOTHING"
        )
        try:
            result = await conn.execute(q, *row.values())
            count = int(result.split()[-1])
            if count:
                summary.record(table, "inserted")
            else:
                summary.record(table, "skipped")
        except Exception as exc:
            logger.error("Failed to insert into %s: %s | row=%s", table, exc, row)
            summary.record(table, "failed")


async def _upsert_composite(
    conn: asyncpg.Connection,
    table: str,
    rows: list[dict[str, Any]],
    conflict_cols: list[str],
    summary: SeedSummary,
) -> None:
    """INSERT rows INTO table ON CONFLICT (col1, col2, ...) DO NOTHING."""
    conflict = ", ".join(conflict_cols)
    for row in rows:
        cols = list(row.keys())
        placeholders = ", ".join(f"${i + 1}" for i in range(len(cols)))
        col_names = ", ".join(cols)
        q = (
            f"INSERT INTO {table} ({col_names}) VALUES ({placeholders}) "
            f"ON CONFLICT ({conflict}) DO NOTHING"
        )
        try:
            result = await conn.execute(q, *row.values())
            count = int(result.split()[-1])
            if count:
                summary.record(table, "inserted")
            else:
                summary.record(table, "skipped")
        except Exception as exc:
            logger.error("Failed to insert into %s: %s | row=%s", table, exc, row)
            summary.record(table, "failed")


# ---------------------------------------------------------------------------
# Main seeding function
# ---------------------------------------------------------------------------

async def seed(dsn: str) -> SeedSummary:
    """Run the full seed against the given PostgreSQL DSN.

    The DSN must be in ``postgresql://`` or ``postgresql+asyncpg://`` format.
    Returns a :class:`SeedSummary` with per-table insert/skip/fail counts.
    """
    if dsn.startswith("postgresql+asyncpg://"):
        dsn = "postgresql://" + dsn[len("postgresql+asyncpg://"):]

    summary = SeedSummary()

    # Import fixtures after DSN check to defer the bcrypt computation.
    from forgeguard.data.seeds.fixtures.users import (  # noqa: PLC0415
        ROLES, PERMISSIONS, ROLE_PERMISSIONS, get_users,
    )
    from forgeguard.data.seeds.fixtures.services import SERVICES  # noqa: PLC0415
    from forgeguard.data.seeds.fixtures.policies import POLICIES, POLICY_RULES  # noqa: PLC0415
    from forgeguard.data.seeds.fixtures.assessments import (  # noqa: PLC0415
        ASSESSMENT, SCORE, FINDINGS, RELEASE_ASSESSMENT, RELEASE_DECISION,
    )
    from forgeguard.data.seeds.fixtures.remediation import RECOMMENDATIONS, EXCEPTIONS  # noqa: PLC0415

    conn = await asyncpg.connect(dsn=dsn)
    try:
        # ---- Roles ----
        await _upsert_none(conn, "roles", ROLES, "id", summary)

        # ---- Permissions ----
        await _upsert_none(conn, "permissions", PERMISSIONS, "id", summary)

        # ---- Users ----
        await _upsert_none(conn, "users", get_users(), "email", summary)

        # ---- Role → Permission matrix ----
        rp_rows = [
            {"role_id": role_id, "permission_id": perm_id}
            for role_id, perm_id in ROLE_PERMISSIONS
        ]
        await _upsert_composite(conn, "role_permissions", rp_rows, ["role_id", "permission_id"], summary)

        # ---- Services ----
        await _upsert_none(conn, "services", SERVICES, "id", summary)

        # ---- Policies ----
        await _upsert_none(conn, "policies", POLICIES, "id", summary)

        # ---- Policy Rules ----
        await _upsert_none(conn, "policy_rules", POLICY_RULES, "id", summary)

        # ---- Assessment ----
        await _upsert_none(conn, "assessments", [ASSESSMENT], "id", summary)

        # ---- Assessment Score ----
        await _upsert_none(conn, "assessment_scores", [SCORE], "id", summary)

        # ---- Findings ----
        await _upsert_none(conn, "findings", FINDINGS, "id", summary)

        # ---- Release Assessment ----
        await _upsert_none(conn, "release_assessments", [RELEASE_ASSESSMENT], "id", summary)

        # ---- Release Decision ----
        await _upsert_none(conn, "release_decisions", [RELEASE_DECISION], "id", summary)

        # ---- Remediation Recommendations ----
        await _upsert_none(conn, "remediation_recommendations", RECOMMENDATIONS, "id", summary)

        # ---- Exceptions ----
        await _upsert_none(conn, "exceptions", EXCEPTIONS, "id", summary)

        # ---- Audit log — seed operation record ----
        audit_row = {
            "actor_role": "platform_admin",
            "action": "seed_data.applied",
            "resource_type": "database",
            "after_state": json.dumps({
                "tables_seeded": list(summary.inserted.keys()),
                "records_inserted": sum(summary.inserted.values()),
            }),
            "correlation_id": str(uuid.uuid4()),
        }
        await _upsert_none(conn, "audit_logs", [audit_row], "correlation_id", summary)

    finally:
        await conn.close()

    summary.log()
    return summary


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _resolve_dsn() -> str:
    """Return the DSN from CLI arg or DATABASE_URL environment variable."""
    import os  # noqa: PLC0415

    if len(sys.argv) > 1:
        return sys.argv[1]
    dsn = os.environ.get("DATABASE_URL", "")
    if not dsn:
        print(
            "Usage: python -m forgeguard.data.seeds.seed_data <postgresql-dsn>\n"
            "       or set DATABASE_URL environment variable",
            file=sys.stderr,
        )
        sys.exit(1)
    return dsn


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    asyncio.run(seed(_resolve_dsn()))
