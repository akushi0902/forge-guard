"""Seed Payment Service demo violation policy rules (WO-055).

Inserts 10 violation-designed policy_rule records across all 5 governance
dimensions.  All inserts use ON CONFLICT DO NOTHING — safe to re-run.

Revision ID: e6f7a8b9c0d1
Revises:     d5e6f7a8b9c0
Create Date: 2026-08-12
"""

from __future__ import annotations

import logging

from alembic import op

logger = logging.getLogger(__name__)

revision: str = "e6f7a8b9c0d1"
down_revision: str | None = "d5e6f7a8b9c0"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Insert demo violation rules idempotently."""
    import asyncio  # noqa: PLC0415

    bind = op.get_bind()
    raw_url = str(bind.engine.url)

    async def _run() -> None:
        import asyncpg  # noqa: PLC0415
        from forgeguard.data.seeds.demo_violations import seed_violation_rules  # noqa: PLC0415

        conn = await asyncpg.connect(raw_url.replace("postgresql+asyncpg://", "postgresql://"))
        try:
            summary = await seed_violation_rules(conn)
            logger.info(
                "Violation rules seeded: %d inserted, %d skipped.",
                summary["inserted"],
                summary["skipped"],
            )
        finally:
            await conn.close()

    asyncio.get_event_loop().run_until_complete(_run())


def downgrade() -> None:
    """Remove demo violation rules by their stable fixture IDs."""
    from forgeguard.data.seeds.demo_violations import ALL_VIOLATION_RULE_IDS  # noqa: PLC0415

    bind = op.get_bind()
    ids = ", ".join(f"'{i}'" for i in ALL_VIOLATION_RULE_IDS)
    bind.execute(f"DELETE FROM policy_rules WHERE id IN ({ids})")
