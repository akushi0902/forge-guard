"""Seed demo data: users, services, policies, assessments, findings, decisions.

Inserts the complete ForgeGuard demo dataset for all six personas.
All inserts use ON CONFLICT DO NOTHING so upgrading an already-seeded
database is safe. Downgrade removes only rows whose IDs match the
seed fixtures — it will not delete data added after seeding.

Revision ID: a7b8c9d0e1f2
Revises:     f6a7b8c9d0e1 (remediation_schema)
Create Date: 2026-08-11 00:06:00 UTC
"""

from __future__ import annotations

import asyncio
import logging
import os
from concurrent.futures import ThreadPoolExecutor

from alembic import op

logger = logging.getLogger(__name__)

revision: str = "a7b8c9d0e1f2"
down_revision: str | None = "f6a7b8c9d0e1"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Run the seed script against the current migration database URL."""
    from alembic import op as _op  # noqa: PLC0415

    # Resolve DSN from Alembic connection.  The engine is already configured
    # by alembic/env.py from get_settings().database_url.
    bind = op.get_bind()
    # NOTE: str(bind.engine.url) masks the password as "***" by design,
    # to keep credentials out of logs/tracebacks. That masked string was
    # being passed straight to a separate asyncpg.connect() call below,
    # which then genuinely tried to authenticate with the literal
    # password "***" — causing InvalidPasswordError. render_as_string
    # with hide_password=False returns the real, connectable DSN.
    raw_url = bind.engine.url.render_as_string(hide_password=False)

    async def _run() -> None:
        from forgeguard.data.seeds.seed_data import seed  # noqa: PLC0415
        summary = await seed(raw_url)
        if summary.failed:
            logger.warning(
                "Seed migration completed with %d failures. "
                "Check logs for details.",
                sum(summary.failed.values()),
            )

    # NOTE: upgrade() runs inside a greenlet spawned by
    # connection.run_sync() in alembic/env.py, on the same OS thread as
    # that file's outer `asyncio.run(run_async_migrations())` call. That
    # outer loop is still "running" (merely paused mid-step via the
    # greenlet switch) for the entire duration of upgrade(), so
    # asyncio.get_event_loop().run_until_complete() fails here with
    # "This event loop is already running". Running the coroutine on a
    # separate thread gives it its own independent event loop, with no
    # relationship to the paused outer one, avoiding the conflict.
    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(asyncio.run, _run()).result()


def downgrade() -> None:
    """Remove seed data rows by their stable fixture IDs."""
    from forgeguard.data.seeds.fixtures.remediation import (  # noqa: PLC0415
        EXCEPTION_API_DOCS_ID, RECOMMENDATION_CVE_ID, RECOMMENDATION_COVERAGE_ID,
    )
    from forgeguard.data.seeds.fixtures.assessments import (  # noqa: PLC0415
        RELEASE_DECISION_ID, RELEASE_ASSESSMENT_ID,
        FINDING_CVE_ID, FINDING_COVERAGE_ID, FINDING_API_DOCS_ID,
        FINDING_RUNBOOK_ID, FINDING_COMPLEXITY_ID,
        SCORE_HEALTH_ID, ASSESSMENT_HEALTH_ID,
    )
    from forgeguard.data.seeds.fixtures.policies import (  # noqa: PLC0415
        RULE_CQ_COMPLEXITY_ID, RULE_CQ_DUPLICATION_ID, RULE_CQ_LINT_ID,
        RULE_TC_UNIT_ID, RULE_TC_INTEGRATION_ID, RULE_TC_BRANCH_ID,
        RULE_SEC_CVE_ID, RULE_SEC_SECRETS_ID, RULE_SEC_SAST_ID,
        RULE_DOC_API_ID, RULE_DOC_RUNBOOK_ID, RULE_DOC_ADR_ID,
        RULE_OPS_ALERTS_ID, RULE_OPS_DASHBOARDS_ID, RULE_OPS_ONBOARDING_ID,
        POLICY_CODE_QUALITY_ID, POLICY_TEST_COVERAGE_ID, POLICY_SECURITY_ID,
        POLICY_DOCUMENTATION_ID, POLICY_OPS_READINESS_ID,
    )
    from forgeguard.data.seeds.fixtures.services import (  # noqa: PLC0415
        SERVICE_PAYMENT_ID, SERVICE_API_GATEWAY_ID, SERVICE_AUTH_ID,
    )
    from forgeguard.data.seeds.fixtures.users import (  # noqa: PLC0415
        USER_DEVELOPER_ID, USER_TECHLEAD_ID, USER_SECURITY_ID,
        USER_ADMIN_ID, USER_MANAGER_ID, USER_OPERATOR_ID,
        ROLE_DEVELOPER_ID, ROLE_TECHLEAD_ID, ROLE_SECURITY_ID,
        ROLE_ADMIN_ID, ROLE_MANAGER_ID, ROLE_OPERATOR_ID,
        PERM_ASSESSMENT_VIEW_ID, PERM_ASSESSMENT_CREATE_ID,
        PERM_POLICY_VIEW_ID, PERM_POLICY_MANAGE_ID,
        PERM_RELEASE_VIEW_ID, PERM_RELEASE_APPROVE_ID,
        PERM_FINDING_VIEW_ID, PERM_EXCEPTION_REQUEST_ID,
        PERM_EXCEPTION_APPROVE_ID, PERM_ADMIN_MANAGE_ID,
    )

    bind = op.get_bind()

    def _ids(*ids: str) -> str:
        return ", ".join(f"'{i}'" for i in ids)

    bind.execute(f"DELETE FROM exceptions WHERE id IN ({_ids(EXCEPTION_API_DOCS_ID)})")
    bind.execute(f"DELETE FROM remediation_recommendations WHERE id IN ({_ids(RECOMMENDATION_CVE_ID, RECOMMENDATION_COVERAGE_ID)})")
    bind.execute(f"DELETE FROM release_decisions WHERE id IN ({_ids(RELEASE_DECISION_ID)})")
    bind.execute(f"DELETE FROM release_assessments WHERE id IN ({_ids(RELEASE_ASSESSMENT_ID)})")
    bind.execute(f"DELETE FROM findings WHERE id IN ({_ids(FINDING_CVE_ID, FINDING_COVERAGE_ID, FINDING_API_DOCS_ID, FINDING_RUNBOOK_ID, FINDING_COMPLEXITY_ID)})")
    bind.execute(f"DELETE FROM assessment_scores WHERE id IN ({_ids(SCORE_HEALTH_ID)})")
    bind.execute(f"DELETE FROM assessments WHERE id IN ({_ids(ASSESSMENT_HEALTH_ID)})")
    bind.execute(f"DELETE FROM policy_rules WHERE id IN ({_ids(RULE_CQ_COMPLEXITY_ID, RULE_CQ_DUPLICATION_ID, RULE_CQ_LINT_ID, RULE_TC_UNIT_ID, RULE_TC_INTEGRATION_ID, RULE_TC_BRANCH_ID, RULE_SEC_CVE_ID, RULE_SEC_SECRETS_ID, RULE_SEC_SAST_ID, RULE_DOC_API_ID, RULE_DOC_RUNBOOK_ID, RULE_DOC_ADR_ID, RULE_OPS_ALERTS_ID, RULE_OPS_DASHBOARDS_ID, RULE_OPS_ONBOARDING_ID)})")
    bind.execute(f"DELETE FROM policies WHERE id IN ({_ids(POLICY_CODE_QUALITY_ID, POLICY_TEST_COVERAGE_ID, POLICY_SECURITY_ID, POLICY_DOCUMENTATION_ID, POLICY_OPS_READINESS_ID)})")
    bind.execute(f"DELETE FROM services WHERE id IN ({_ids(SERVICE_PAYMENT_ID, SERVICE_API_GATEWAY_ID, SERVICE_AUTH_ID)})")
    bind.execute(f"DELETE FROM role_permissions WHERE role_id IN ({_ids(ROLE_DEVELOPER_ID, ROLE_TECHLEAD_ID, ROLE_SECURITY_ID, ROLE_ADMIN_ID, ROLE_MANAGER_ID, ROLE_OPERATOR_ID)})")
    bind.execute(f"DELETE FROM users WHERE id IN ({_ids(USER_DEVELOPER_ID, USER_TECHLEAD_ID, USER_SECURITY_ID, USER_ADMIN_ID, USER_MANAGER_ID, USER_OPERATOR_ID)})")
    bind.execute(f"DELETE FROM permissions WHERE id IN ({_ids(PERM_ASSESSMENT_VIEW_ID, PERM_ASSESSMENT_CREATE_ID, PERM_POLICY_VIEW_ID, PERM_POLICY_MANAGE_ID, PERM_RELEASE_VIEW_ID, PERM_RELEASE_APPROVE_ID, PERM_FINDING_VIEW_ID, PERM_EXCEPTION_REQUEST_ID, PERM_EXCEPTION_APPROVE_ID, PERM_ADMIN_MANAGE_ID)})")
    bind.execute(f"DELETE FROM roles WHERE id IN ({_ids(ROLE_DEVELOPER_ID, ROLE_TECHLEAD_ID, ROLE_SECURITY_ID, ROLE_ADMIN_ID, ROLE_MANAGER_ID, ROLE_OPERATOR_ID)})")
