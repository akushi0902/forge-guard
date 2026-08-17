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
import threading
from typing import Any, Coroutine

import sqlalchemy as sa
from alembic import op

logger = logging.getLogger(__name__)

revision: str = "a7b8c9d0e1f2"
down_revision: str | None = "f6a7b8c9d0e1"
branch_labels: str | None = None
depends_on: str | None = None


def _run_coro_isolated(coro: Coroutine[Any, Any, Any]) -> Any:
    """Run *coro* to completion on a fresh event loop in a dedicated thread.

    Alembic's env.py already drives migrations under a running event loop
    (``asyncio.run(run_async_migrations())`` -> ``connection.run_sync(...)``),
    so calling ``run_until_complete`` on the current thread raises
    ``RuntimeError: This event loop is already running``. Executing the
    coroutine on its own loop in a separate thread avoids that collision.

    NOTE: ``seed()`` must create/own its own async engine from the DSN and
    must NOT reuse Alembic's bound connection (it doesn't — it takes a URL).
    """
    result: dict[str, Any] = {}
    error: dict[str, BaseException] = {}

    def _worker() -> None:
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            result["value"] = loop.run_until_complete(coro)
        except BaseException as exc:  # noqa: BLE001 - re-raised on caller thread
            error["value"] = exc
        finally:
            try:
                loop.run_until_complete(loop.shutdown_asyncgens())
            finally:
                asyncio.set_event_loop(None)
                loop.close()

    thread = threading.Thread(target=_worker, name="forgeguard-seed", daemon=True)
    thread.start()
    thread.join()

    if "value" in error:
        raise error["value"]
    return result.get("value")


def upgrade() -> None:
    """Run the seed script against the current migration database URL."""
    # Resolve DSN from the Alembic connection. The engine is already configured
    # by alembic/env.py from get_settings().database_url.
    bind = op.get_bind()
    raw_url = str(bind.engine.url)

    async def _run() -> None:
        from forgeguard.data.seeds.seed_data import seed  # noqa: PLC0415

        summary = await seed(raw_url)
        if summary.failed:
            logger.warning(
                "Seed migration completed with %d failures. "
                "Check logs for details.",
                sum(summary.failed.values()),
            )

    # Do NOT re-enter Alembic's already-running loop; run on an isolated loop.
    _run_coro_isolated(_run())


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

    def _delete(table: str, column: str, ids: tuple[str, ...]) -> None:
        """Parameterised, dialect-safe bulk delete by ID list."""
        if not ids:
            return
        stmt = sa.text(
            f"DELETE FROM {table} WHERE {column} IN :ids"
        ).bindparams(sa.bindparam("ids", expanding=True))
        bind.execute(stmt, {"ids": list(ids)})

    # Delete in FK-safe order (children first, parents last).
    _delete("exceptions", "id", (EXCEPTION_API_DOCS_ID,))
    _delete("remediation_recommendations", "id",
            (RECOMMENDATION_CVE_ID, RECOMMENDATION_COVERAGE_ID))
    _delete("release_decisions", "id", (RELEASE_DECISION_ID,))
    _delete("release_assessments", "id", (RELEASE_ASSESSMENT_ID,))
    _delete("findings", "id",
            (FINDING_CVE_ID, FINDING_COVERAGE_ID, FINDING_API_DOCS_ID,
             FINDING_RUNBOOK_ID, FINDING_COMPLEXITY_ID))
    _delete("assessment_scores", "id", (SCORE_HEALTH_ID,))
    _delete("assessments", "id", (ASSESSMENT_HEALTH_ID,))
    _delete("policy_rules", "id",
            (RULE_CQ_COMPLEXITY_ID, RULE_CQ_DUPLICATION_ID, RULE_CQ_LINT_ID,
             RULE_TC_UNIT_ID, RULE_TC_INTEGRATION_ID, RULE_TC_BRANCH_ID,
             RULE_SEC_CVE_ID, RULE_SEC_SECRETS_ID, RULE_SEC_SAST_ID,
             RULE_DOC_API_ID, RULE_DOC_RUNBOOK_ID, RULE_DOC_ADR_ID,
             RULE_OPS_ALERTS_ID, RULE_OPS_DASHBOARDS_ID, RULE_OPS_ONBOARDING_ID))
    _delete("policies", "id",
            (POLICY_CODE_QUALITY_ID, POLICY_TEST_COVERAGE_ID, POLICY_SECURITY_ID,
             POLICY_DOCUMENTATION_ID, POLICY_OPS_READINESS_ID))
    _delete("services", "id",
            (SERVICE_PAYMENT_ID, SERVICE_API_GATEWAY_ID, SERVICE_AUTH_ID))
    _delete("role_permissions", "role_id",
            (ROLE_DEVELOPER_ID, ROLE_TECHLEAD_ID, ROLE_SECURITY_ID,
             ROLE_ADMIN_ID, ROLE_MANAGER_ID, ROLE_OPERATOR_ID))
    _delete("users", "id",
            (USER_DEVELOPER_ID, USER_TECHLEAD_ID, USER_SECURITY_ID,
             USER_ADMIN_ID, USER_MANAGER_ID, USER_OPERATOR_ID))
    _delete("permissions", "id",
            (PERM_ASSESSMENT_VIEW_ID, PERM_ASSESSMENT_CREATE_ID,
             PERM_POLICY_VIEW_ID, PERM_POLICY_MANAGE_ID,
             PERM_RELEASE_VIEW_ID, PERM_RELEASE_APPROVE_ID,
             PERM_FINDING_VIEW_ID, PERM_EXCEPTION_REQUEST_ID,
             PERM_EXCEPTION_APPROVE_ID, PERM_ADMIN_MANAGE_ID))
    _delete("roles", "id",
            (ROLE_DEVELOPER_ID, ROLE_TECHLEAD_ID, ROLE_SECURITY_ID,
             ROLE_ADMIN_ID, ROLE_MANAGER_ID, ROLE_OPERATOR_ID))
