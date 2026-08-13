"""Integration tests for WO-014 seed data fixtures.

Verifies that after running the seed script:
  - All 6 demo users exist with correct roles
  - All 3 demo services exist (Payment Service is_demo=True)
  - All 5 policies and 15 rules exist with required severity distribution
  - Payment Service assessment has Health Score 55–70
  - At least 5 findings across at least 3 dimensions, including 1 critical security
  - Release decision CONDITIONAL_APPROVE exists (was_escalated=True)
  - 2 remediation recommendations (ai_generated + template_fallback)
  - 1 approved exception with future expiry date
  - Running seed twice produces no duplicate records (idempotency)

Run:
    cd backend && pytest tests/data/test_seed_data.py -v -m integration
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Module-scoped seed fixture: seed once, all tests share the same pool
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
async def pool(asyncpg_pool, db_url, apply_migrations):
    """Seed the database once per test module and return the pool."""
    from forgeguard.data.seeds.seed_data import seed  # noqa: PLC0415

    await seed(db_url)
    return asyncpg_pool


@pytest.fixture(scope="module")
def seed_dsn(db_url):
    return db_url


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDemoUsers:
    async def test_six_users_exist(self, pool):
        async with pool.acquire() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM users WHERE email LIKE '%@forgeguard.demo'"
            )
        assert count == 6, f"Expected 6 demo users, got {count}"

    async def test_all_roles_present(self, pool):
        expected_roles = {
            "developer", "tech_lead", "security_reviewer",
            "platform_admin", "engineering_manager", "operator",
        }
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT role FROM users WHERE email LIKE '%@forgeguard.demo'"
            )
        actual_roles = {r["role"] for r in rows}
        assert actual_roles == expected_roles

    async def test_user_emails_match_spec(self, pool):
        expected_emails = {
            "developer@forgeguard.demo",
            "techlead@forgeguard.demo",
            "security@forgeguard.demo",
            "admin@forgeguard.demo",
            "manager@forgeguard.demo",
            "operator@forgeguard.demo",
        }
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT email FROM users WHERE email LIKE '%@forgeguard.demo'"
            )
        actual = {r["email"] for r in rows}
        assert actual == expected_emails

    async def test_passwords_are_bcrypt_cost12(self, pool):
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT password_hash FROM users WHERE email LIKE '%@forgeguard.demo'"
            )
        for row in rows:
            h = row["password_hash"]
            assert h.startswith("$2b$12$"), (
                f"Expected bcrypt cost-12 hash, got prefix: {h[:10]}"
            )

    async def test_all_users_active(self, pool):
        async with pool.acquire() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM users "
                "WHERE email LIKE '%@forgeguard.demo' AND is_active = TRUE"
            )
        assert count == 6


class TestRBACMatrix:
    async def test_six_roles_exist(self, pool):
        from forgeguard.data.seeds.fixtures.users import ROLES  # noqa: PLC0415

        async with pool.acquire() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM roles WHERE id = ANY($1::uuid[])",
                [r["id"] for r in ROLES],
            )
        assert count == 6

    async def test_ten_permissions_exist(self, pool):
        from forgeguard.data.seeds.fixtures.users import PERMISSIONS  # noqa: PLC0415

        async with pool.acquire() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM permissions WHERE id = ANY($1::uuid[])",
                [p["id"] for p in PERMISSIONS],
            )
        assert count == 10

    async def test_role_permissions_populated(self, pool):
        async with pool.acquire() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM role_permissions rp "
                "JOIN roles r ON r.id = rp.role_id "
                "WHERE r.name IN ('developer','tech_lead','security_reviewer',"
                "'platform_admin','engineering_manager','operator')"
            )
        assert count > 0

    async def test_admin_has_all_permissions(self, pool):
        from forgeguard.data.seeds.fixtures.users import ROLE_ADMIN_ID  # noqa: PLC0415

        async with pool.acquire() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM role_permissions WHERE role_id = $1",
                ROLE_ADMIN_ID,
            )
        assert count == 10, f"platform_admin should have all 10 permissions, got {count}"


class TestDemoServices:
    async def test_three_services_exist(self, pool):
        from forgeguard.data.seeds.fixtures.services import (  # noqa: PLC0415
            SERVICE_PAYMENT_ID, SERVICE_API_GATEWAY_ID, SERVICE_AUTH_ID,
        )
        async with pool.acquire() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM services WHERE id = ANY($1::uuid[])",
                [SERVICE_PAYMENT_ID, SERVICE_API_GATEWAY_ID, SERVICE_AUTH_ID],
            )
        assert count == 3

    async def test_payment_service_is_demo(self, pool):
        from forgeguard.data.seeds.fixtures.services import SERVICE_PAYMENT_ID  # noqa: PLC0415

        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT is_demo, name FROM services WHERE id = $1", SERVICE_PAYMENT_ID
            )
        assert row is not None
        assert row["is_demo"] is True
        assert "Payment" in row["name"]

    async def test_services_have_repository_url(self, pool):
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT repository_url FROM services "
                "WHERE repository_url LIKE '%forgeguard.demo%'"
            )
        assert len(rows) == 3


class TestPoliciesAndRules:
    async def test_five_policies_exist(self, pool):
        from forgeguard.data.seeds.fixtures.policies import (  # noqa: PLC0415
            POLICY_CODE_QUALITY_ID, POLICY_TEST_COVERAGE_ID, POLICY_SECURITY_ID,
            POLICY_DOCUMENTATION_ID, POLICY_OPS_READINESS_ID,
        )
        async with pool.acquire() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM policies WHERE id = ANY($1::uuid[])",
                [POLICY_CODE_QUALITY_ID, POLICY_TEST_COVERAGE_ID, POLICY_SECURITY_ID,
                 POLICY_DOCUMENTATION_ID, POLICY_OPS_READINESS_ID],
            )
        assert count == 5

    async def test_all_dimensions_covered(self, pool):
        from forgeguard.data.seeds.fixtures.policies import (  # noqa: PLC0415
            POLICY_CODE_QUALITY_ID, POLICY_TEST_COVERAGE_ID, POLICY_SECURITY_ID,
            POLICY_DOCUMENTATION_ID, POLICY_OPS_READINESS_ID,
        )
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT dimension FROM policies WHERE id = ANY($1::uuid[])",
                [POLICY_CODE_QUALITY_ID, POLICY_TEST_COVERAGE_ID, POLICY_SECURITY_ID,
                 POLICY_DOCUMENTATION_ID, POLICY_OPS_READINESS_ID],
            )
        dims = {r["dimension"] for r in rows}
        expected = {"code_quality", "test_coverage", "security", "documentation", "operations_readiness"}
        assert dims == expected

    async def test_fifteen_policy_rules_exist(self, pool):
        from forgeguard.data.seeds.fixtures.policies import POLICY_RULES  # noqa: PLC0415

        rule_ids = [r["id"] for r in POLICY_RULES]
        async with pool.acquire() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM policy_rules WHERE id = ANY($1::uuid[])",
                rule_ids,
            )
        assert count >= 15

    async def test_severity_distribution(self, pool):
        from forgeguard.data.seeds.fixtures.policies import POLICY_RULES  # noqa: PLC0415

        rule_ids = [r["id"] for r in POLICY_RULES]
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT severity, COUNT(*) AS cnt FROM policy_rules "
                "WHERE id = ANY($1::uuid[]) GROUP BY severity",
                rule_ids,
            )
        counts = {r["severity"]: r["cnt"] for r in rows}
        assert counts.get("critical", 0) >= 1, "Need at least 1 critical rule"
        assert counts.get("high", 0) >= 2, "Need at least 2 high rules"
        assert counts.get("medium", 0) >= 3, "Need at least 3 medium rules"
        assert counts.get("low", 0) >= 2, "Need at least 2 low rules"


class TestAssessmentAndFindings:
    async def test_health_assessment_exists_completed(self, pool):
        from forgeguard.data.seeds.fixtures.assessments import ASSESSMENT_HEALTH_ID  # noqa: PLC0415

        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT status, assessment_type FROM assessments WHERE id = $1",
                ASSESSMENT_HEALTH_ID,
            )
        assert row is not None
        assert row["status"] == "completed"
        assert row["assessment_type"] == "health_check"

    async def test_health_score_between_55_and_70(self, pool):
        from forgeguard.data.seeds.fixtures.assessments import SCORE_HEALTH_ID  # noqa: PLC0415

        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT overall_score FROM assessment_scores WHERE id = $1",
                SCORE_HEALTH_ID,
            )
        assert row is not None
        score = float(row["overall_score"])
        assert 55 <= score <= 70, f"Health score {score} not in range 55-70"

    async def test_five_findings_exist(self, pool):
        from forgeguard.data.seeds.fixtures.assessments import ASSESSMENT_HEALTH_ID  # noqa: PLC0415

        async with pool.acquire() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM findings WHERE assessment_id = $1",
                ASSESSMENT_HEALTH_ID,
            )
        assert count >= 5

    async def test_findings_span_three_dimensions(self, pool):
        from forgeguard.data.seeds.fixtures.assessments import ASSESSMENT_HEALTH_ID  # noqa: PLC0415

        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT DISTINCT dimension FROM findings WHERE assessment_id = $1",
                ASSESSMENT_HEALTH_ID,
            )
        dims = {r["dimension"] for r in rows}
        assert len(dims) >= 3, f"Expected 3+ dimensions, got {dims}"

    async def test_at_least_one_critical_security_finding(self, pool):
        from forgeguard.data.seeds.fixtures.assessments import ASSESSMENT_HEALTH_ID  # noqa: PLC0415

        async with pool.acquire() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM findings "
                "WHERE assessment_id = $1 AND severity = 'critical' AND dimension = 'security'",
                ASSESSMENT_HEALTH_ID,
            )
        assert count >= 1

    async def test_findings_linked_to_policy_rules(self, pool):
        from forgeguard.data.seeds.fixtures.assessments import ASSESSMENT_HEALTH_ID  # noqa: PLC0415

        async with pool.acquire() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM findings f "
                "JOIN policy_rules pr ON pr.id = f.policy_rule_id "
                "WHERE f.assessment_id = $1",
                ASSESSMENT_HEALTH_ID,
            )
        assert count >= 5


class TestReleaseDecision:
    async def test_release_assessment_exists(self, pool):
        from forgeguard.data.seeds.fixtures.assessments import RELEASE_ASSESSMENT_ID  # noqa: PLC0415

        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT status FROM release_assessments WHERE id = $1",
                RELEASE_ASSESSMENT_ID,
            )
        assert row is not None
        assert row["status"] == "completed"

    async def test_conditional_approve_decision(self, pool):
        from forgeguard.data.seeds.fixtures.assessments import RELEASE_DECISION_ID  # noqa: PLC0415

        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT decision, was_escalated FROM release_decisions WHERE id = $1",
                RELEASE_DECISION_ID,
            )
        assert row is not None
        assert row["decision"] == "CONDITIONAL_APPROVE"
        assert row["was_escalated"] is True


class TestRemediationAndExceptions:
    async def test_two_recommendations_exist(self, pool):
        from forgeguard.data.seeds.fixtures.remediation import (  # noqa: PLC0415
            RECOMMENDATION_CVE_ID, RECOMMENDATION_COVERAGE_ID,
        )
        async with pool.acquire() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM remediation_recommendations "
                "WHERE id = ANY($1::uuid[])",
                [RECOMMENDATION_CVE_ID, RECOMMENDATION_COVERAGE_ID],
            )
        assert count == 2

    async def test_recommendation_sources_vary(self, pool):
        from forgeguard.data.seeds.fixtures.remediation import (  # noqa: PLC0415
            RECOMMENDATION_CVE_ID, RECOMMENDATION_COVERAGE_ID,
        )
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT source FROM remediation_recommendations "
                "WHERE id = ANY($1::uuid[])",
                [RECOMMENDATION_CVE_ID, RECOMMENDATION_COVERAGE_ID],
            )
        sources = {r["source"] for r in rows}
        assert "ai_generated" in sources
        assert "template_fallback" in sources

    async def test_ai_recommendation_confidence_range(self, pool):
        from forgeguard.data.seeds.fixtures.remediation import RECOMMENDATION_CVE_ID  # noqa: PLC0415

        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT confidence_score FROM remediation_recommendations WHERE id = $1",
                RECOMMENDATION_CVE_ID,
            )
        assert row is not None
        score = float(row["confidence_score"])
        assert 0.80 <= score <= 0.90

    async def test_approved_exception_exists_with_future_expiry(self, pool):
        from forgeguard.data.seeds.fixtures.remediation import EXCEPTION_API_DOCS_ID  # noqa: PLC0415
        from datetime import datetime, timezone  # noqa: PLC0415

        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT status, expires_at FROM exceptions WHERE id = $1",
                EXCEPTION_API_DOCS_ID,
            )
        assert row is not None
        assert row["status"] == "approved"
        assert row["expires_at"] > datetime.now(tz=timezone.utc)


class TestIdempotency:
    async def test_running_seed_twice_produces_no_duplicates(self, pool, seed_dsn):
        """Second run should produce 0 new rows (all skipped via ON CONFLICT DO NOTHING)."""
        from forgeguard.data.seeds.seed_data import seed  # noqa: PLC0415

        async with pool.acquire() as conn:
            before_users = await conn.fetchval(
                "SELECT COUNT(*) FROM users WHERE email LIKE '%@forgeguard.demo'"
            )
            before_services = await conn.fetchval(
                "SELECT COUNT(*) FROM services WHERE is_demo = TRUE"
            )
            before_findings = await conn.fetchval("SELECT COUNT(*) FROM findings")

        summary = await seed(seed_dsn)

        async with pool.acquire() as conn:
            after_users = await conn.fetchval(
                "SELECT COUNT(*) FROM users WHERE email LIKE '%@forgeguard.demo'"
            )
            after_services = await conn.fetchval(
                "SELECT COUNT(*) FROM services WHERE is_demo = TRUE"
            )
            after_findings = await conn.fetchval("SELECT COUNT(*) FROM findings")

        assert after_users == before_users, "User count changed on second seed run"
        assert after_services == before_services, "Service count changed on second seed run"
        assert after_findings == before_findings, "Findings count changed on second seed run"

        for table, count in summary.inserted.items():
            if table == "audit_logs":
                continue  # audit log always writes a new record (unique correlation_id)
            assert count == 0, (
                f"Table '{table}': expected 0 inserts on second run, got {count}"
            )
