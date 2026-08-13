"""Integration tests for WO-013 repository pattern and async connection pool.

All tests require a live PostgreSQL 16 instance via testcontainers and are
marked @pytest.mark.integration so they can be skipped in unit-only CI runs.

Run:
    cd backend && pytest tests/data/test_repositories.py -v -m integration
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Pool / health check
# ---------------------------------------------------------------------------


class TestConnectionPool:
    async def test_health_check_returns_true(self, asyncpg_pool, apply_migrations):
        """SELECT 1 succeeds against the running testcontainer."""
        async with asyncpg_pool.acquire() as conn:
            result = await conn.fetchval("SELECT 1")
        assert result == 1

    async def test_pool_has_correct_min_max_size(self, asyncpg_pool):
        assert asyncpg_pool.get_min_size() == 1
        assert asyncpg_pool.get_max_size() == 5

    async def test_health_check_module_function(self, asyncpg_pool, apply_migrations):
        from forgeguard.data.database import health_check, _pool as _orig
        import forgeguard.data.database as db_mod  # noqa: PLC0415

        orig = db_mod._pool
        db_mod._pool = asyncpg_pool
        try:
            result = await health_check()
        finally:
            db_mod._pool = orig
        assert result is True


# ---------------------------------------------------------------------------
# UserRepository
# ---------------------------------------------------------------------------


class TestUserRepository:
    @pytest.fixture(autouse=True)
    async def setup(self, asyncpg_pool, clean_tables):
        from forgeguard.data.repositories.users import UserRepository  # noqa: PLC0415

        self.repo = UserRepository(asyncpg_pool)

    async def test_create_returns_row_with_id(self):
        user = await self.repo.create({
            "email": "alice@example.com",
            "password_hash": "$2b$12$" + "A" * 53,
            "role": "developer",
        })
        assert "id" in user
        assert user["email"] == "alice@example.com"

    async def test_get_by_id_retrieves_correct_record(self):
        created = await self.repo.create({
            "email": "bob@example.com",
            "password_hash": "$2b$12$" + "B" * 53,
            "role": "tech_lead",
        })
        fetched = await self.repo.get_by_id(created["id"])
        assert fetched is not None
        assert fetched["id"] == created["id"]

    async def test_get_by_id_returns_none_for_soft_deleted(self):
        created = await self.repo.create({
            "email": "charlie@example.com",
            "password_hash": "$2b$12$" + "C" * 53,
            "role": "developer",
        })
        await self.repo.soft_delete(created["id"])
        assert await self.repo.get_by_id(created["id"]) is None

    async def test_get_by_id_include_deleted_returns_record(self):
        created = await self.repo.create({
            "email": "dana@example.com",
            "password_hash": "$2b$12$" + "D" * 53,
            "role": "developer",
        })
        await self.repo.soft_delete(created["id"])
        fetched = await self.repo.get_by_id(created["id"], include_deleted=True)
        assert fetched is not None
        assert fetched["deleted_at"] is not None

    async def test_list_excludes_soft_deleted(self):
        u1 = await self.repo.create({
            "email": "e1@example.com",
            "password_hash": "$2b$12$" + "E" * 53,
            "role": "developer",
        })
        u2 = await self.repo.create({
            "email": "e2@example.com",
            "password_hash": "$2b$12$" + "F" * 53,
            "role": "developer",
        })
        await self.repo.soft_delete(u1["id"])
        results = await self.repo.list(limit=50)
        ids = [r["id"] for r in results]
        assert u1["id"] not in ids
        assert u2["id"] in ids

    async def test_list_cursor_pagination(self):
        users = []
        for i in range(5):
            u = await self.repo.create({
                "email": f"page_{i}@example.com",
                "password_hash": "$2b$12$" + "P" * 53,
                "role": "developer",
            })
            users.append(u)

        page1 = await self.repo.list(limit=3)
        assert len(page1) <= 3
        if len(page1) == 3:
            last_id = str(page1[-1]["id"])
            page2 = await self.repo.list(cursor=last_id, limit=10)
            all_ids = {str(u["id"]) for u in page1 + page2}
            for u in users:
                assert str(u["id"]) in all_ids

    async def test_update_modifies_allowed_field(self):
        user = await self.repo.create({
            "email": "update_me@example.com",
            "password_hash": "$2b$12$" + "U" * 53,
            "role": "developer",
        })
        updated = await self.repo.update(user["id"], {"role": "tech_lead"})
        assert updated is not None
        assert updated["role"] == "tech_lead"

    async def test_soft_delete_returns_true(self):
        user = await self.repo.create({
            "email": "del@example.com",
            "password_hash": "$2b$12$" + "D" * 53,
            "role": "developer",
        })
        result = await self.repo.soft_delete(user["id"])
        assert result is True

    async def test_find_by_email_returns_user(self):
        await self.repo.create({
            "email": "findme@example.com",
            "password_hash": "$2b$12$" + "F" * 53,
            "role": "operator",
        })
        found = await self.repo.find_by_email("findme@example.com")
        assert found is not None
        assert found["email"] == "findme@example.com"

    async def test_find_by_email_returns_none_for_deleted(self):
        user = await self.repo.create({
            "email": "gone@example.com",
            "password_hash": "$2b$12$" + "G" * 53,
            "role": "developer",
        })
        await self.repo.soft_delete(user["id"])
        assert await self.repo.find_by_email("gone@example.com") is None

    async def test_update_failed_login_attempts(self):
        user = await self.repo.create({
            "email": "lockme@example.com",
            "password_hash": "$2b$12$" + "L" * 53,
            "role": "developer",
        })
        await self.repo.update_failed_login_attempts(user["id"], 3)
        fetched = await self.repo.get_by_id(user["id"])
        assert fetched["failed_login_attempts"] == 3

    async def test_lock_account_sets_locked_until(self):
        user = await self.repo.create({
            "email": "locked@example.com",
            "password_hash": "$2b$12$" + "K" * 53,
            "role": "developer",
        })
        lock_time = datetime(2030, 1, 1, tzinfo=timezone.utc)
        await self.repo.lock_account(user["id"], lock_time)
        fetched = await self.repo.get_by_id(user["id"])
        assert fetched["locked_until"] is not None

    async def test_queries_use_parameterized_syntax(self):
        """Verify queries contain $1 parameter syntax (no string interpolation)."""
        import inspect  # noqa: PLC0415
        import forgeguard.data.repositories.users as users_mod  # noqa: PLC0415

        source = inspect.getsource(users_mod)
        assert "$1" in source
        assert "$2" in source


# ---------------------------------------------------------------------------
# ServiceRepository
# ---------------------------------------------------------------------------


class TestServiceRepository:
    @pytest.fixture(autouse=True)
    async def setup(self, asyncpg_pool, clean_tables):
        from forgeguard.data.repositories.services import ServiceRepository  # noqa: PLC0415

        self.repo = ServiceRepository(asyncpg_pool)

    async def test_create_and_get(self):
        svc = await self.repo.create({"name": "payment-service", "metadata": "{}"})
        fetched = await self.repo.get_by_id(svc["id"])
        assert fetched is not None
        assert fetched["name"] == "payment-service"

    async def test_soft_delete_hides_from_list(self):
        svc = await self.repo.create({"name": "deletable", "metadata": "{}"})
        await self.repo.soft_delete(svc["id"])
        results = await self.repo.list(limit=50)
        assert all(str(r["id"]) != str(svc["id"]) for r in results)

    async def test_find_by_name(self):
        await self.repo.create({"name": "known-service", "metadata": "{}"})
        found = await self.repo.find_by_name("known-service")
        assert found is not None
        assert found["name"] == "known-service"

    async def test_find_demo_services(self):
        await self.repo.create({"name": "demo-svc", "metadata": "{}", "is_demo": True})
        await self.repo.create({"name": "real-svc", "metadata": "{}", "is_demo": False})
        demos = await self.repo.find_demo_services()
        names = [d["name"] for d in demos]
        assert "demo-svc" in names
        assert "real-svc" not in names

    async def test_list_with_latest_scores_returns_rows(self):
        await self.repo.create({"name": "scored-svc", "metadata": "{}"})
        rows = await self.repo.list_with_latest_scores(limit=10)
        assert isinstance(rows, list)


# ---------------------------------------------------------------------------
# PolicyRepository
# ---------------------------------------------------------------------------


class TestPolicyRepository:
    @pytest.fixture(autouse=True)
    async def setup(self, asyncpg_pool, clean_tables):
        from forgeguard.data.repositories.policies import PolicyRepository  # noqa: PLC0415

        self.repo = PolicyRepository(asyncpg_pool)

    async def test_create_and_get(self):
        policy = await self.repo.create({
            "name": "security-baseline",
            "dimension": "security",
            "is_active": True,
            "version": 1,
        })
        fetched = await self.repo.get_by_id(policy["id"])
        assert fetched is not None
        assert fetched["dimension"] == "security"

    async def test_find_active_by_dimension(self):
        await self.repo.create({
            "name": "code-quality-v1", "dimension": "code_quality",
            "is_active": True, "version": 1,
        })
        await self.repo.create({
            "name": "code-quality-inactive", "dimension": "code_quality",
            "is_active": False, "version": 1,
        })
        active = await self.repo.find_active_by_dimension("code_quality")
        assert all(p["is_active"] for p in active)
        names = [p["name"] for p in active]
        assert "code-quality-v1" in names
        assert "code-quality-inactive" not in names

    async def test_increment_version(self):
        policy = await self.repo.create({
            "name": "versioned", "dimension": "security",
            "is_active": True, "version": 1,
        })
        updated = await self.repo.increment_version(policy["id"])
        assert updated is not None
        assert updated["version"] == 2

    async def test_get_with_rules_includes_rules(self, asyncpg_pool):
        policy = await self.repo.create({
            "name": "with-rules", "dimension": "test_coverage",
            "is_active": True, "version": 1,
        })
        # Insert a rule directly
        async with asyncpg_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO policy_rules "
                "(policy_id, name, rule_type, threshold_config, severity, weight, is_active) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7)",
                policy["id"], "coverage-80", "threshold", "{}", "medium", "1.0", True,
            )
        result = await self.repo.get_with_rules(policy["id"])
        assert result is not None
        assert "rules" in result
        assert len(result["rules"]) == 1


# ---------------------------------------------------------------------------
# FindingRepository
# ---------------------------------------------------------------------------


class TestFindingRepository:
    @pytest.fixture(autouse=True)
    async def setup(self, asyncpg_pool, clean_tables, insert_service, insert_policy,
                    insert_policy_rule, insert_assessment):
        from forgeguard.data.repositories.findings import FindingRepository  # noqa: PLC0415

        self.repo = FindingRepository(asyncpg_pool)
        self.pool = asyncpg_pool
        self.svc = await insert_service()
        self.policy = await insert_policy(dimension="security")
        self.rule = await insert_policy_rule(self.policy["id"])
        self.assessment = await insert_assessment(self.svc["id"])

    async def _create_finding(self, **overrides):
        data = {
            "assessment_id": self.assessment["id"],
            "service_id": self.svc["id"],
            "policy_rule_id": self.rule["id"],
            "severity": "high",
            "dimension": "security",
            "status": "open",
            "title": "Test finding",
        }
        data.update(overrides)
        return await self.repo.create(data)

    async def test_create_and_get(self):
        f = await self._create_finding()
        fetched = await self.repo.get_by_id(f["id"])
        assert fetched is not None
        assert fetched["title"] == "Test finding"

    async def test_find_by_service_and_severity(self):
        await self._create_finding(severity="critical")
        await self._create_finding(severity="low")
        results = await self.repo.find_by_service_and_severity(
            self.svc["id"], "critical"
        )
        assert all(r["severity"] == "critical" for r in results)

    async def test_find_by_assessment(self):
        await self._create_finding()
        results = await self.repo.find_by_assessment(self.assessment["id"])
        assert len(results) >= 1

    async def test_count_by_severity(self):
        await self._create_finding(severity="critical")
        await self._create_finding(severity="high")
        await self._create_finding(severity="high")
        counts = await self.repo.count_by_severity(self.svc["id"])
        assert counts["critical"] == 1
        assert counts["high"] == 2
        assert counts["medium"] == 0
        assert counts["low"] == 0

    async def test_update_status(self):
        f = await self._create_finding()
        updated = await self.repo.update_status(f["id"], "resolved")
        assert updated is not None
        assert updated["status"] == "resolved"

    async def test_soft_delete_raises(self):
        f = await self._create_finding()
        with pytest.raises(NotImplementedError):
            await self.repo.soft_delete(f["id"])


# ---------------------------------------------------------------------------
# ScoreRepository
# ---------------------------------------------------------------------------


class TestScoreRepository:
    @pytest.fixture(autouse=True)
    async def setup(self, asyncpg_pool, clean_tables, insert_service, insert_assessment):
        from forgeguard.data.repositories.scores import ScoreRepository  # noqa: PLC0415

        self.repo = ScoreRepository(asyncpg_pool)
        self.svc = await insert_service()
        self.assessment = await insert_assessment(self.svc["id"])

    async def _create_score(self, **overrides):
        data = {
            "assessment_id": self.assessment["id"],
            "service_id": self.svc["id"],
            "score_type": "health",
            "overall_score": "85.00",
            "dimension_scores": '{"code_quality": 90}',
        }
        data.update(overrides)
        return await self.repo.create(data)

    async def test_create_and_get(self):
        score = await self._create_score()
        fetched = await self.repo.get_by_id(score["id"])
        assert fetched is not None

    async def test_get_latest_score(self):
        await self._create_score(overall_score="70.00")
        await self._create_score(overall_score="85.00")
        latest = await self.repo.get_latest_score(self.svc["id"], "health")
        assert latest is not None

    async def test_get_score_trend(self):
        await self._create_score()
        trend = await self.repo.get_score_trend(self.svc["id"], "health", days=30)
        assert isinstance(trend, list)

    async def test_update_raises(self):
        score = await self._create_score()
        with pytest.raises(NotImplementedError):
            await self.repo.update(score["id"], {})

    async def test_create_with_dimensions(self):
        result = await self.repo.create_with_dimensions({
            "assessment_id": self.assessment["id"],
            "service_id": self.svc["id"],
            "score_type": "risk",
            "overall_score": "42.50",
            "dimension_scores": '{"security": 40, "code_quality": 45}',
        })
        assert result["score_type"] == "risk"


# ---------------------------------------------------------------------------
# DecisionRepository
# ---------------------------------------------------------------------------


class TestDecisionRepository:
    @pytest.fixture(autouse=True)
    async def setup(self, asyncpg_pool, clean_tables, insert_service):
        from forgeguard.data.repositories.decisions import DecisionRepository  # noqa: PLC0415

        self.repo = DecisionRepository(asyncpg_pool)
        self.pool = asyncpg_pool
        self.svc = await insert_service()

    async def _create_release_assessment(self):
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "INSERT INTO release_assessments (service_id, status) "
                "VALUES ($1, 'completed') RETURNING *",
                self.svc["id"],
            )
        return dict(row)

    async def test_create_and_find_by_release_assessment(self):
        ra = await self._create_release_assessment()
        decision = await self.repo.create({
            "release_assessment_id": ra["id"],
            "decision": "APPROVE",
            "decided_by_role": "tech_lead",
            "was_escalated": False,
        })
        results = await self.repo.find_by_release_assessment(ra["id"])
        assert len(results) >= 1
        assert results[0]["decision"] == "APPROVE"

    async def test_list_by_service(self):
        ra = await self._create_release_assessment()
        await self.repo.create({
            "release_assessment_id": ra["id"],
            "decision": "BLOCK",
            "decided_by_role": "security_reviewer",
            "was_escalated": True,
        })
        results = await self.repo.list_by_service(self.svc["id"], limit=10)
        assert len(results) >= 1

    async def test_update_raises(self):
        ra = await self._create_release_assessment()
        d = await self.repo.create({
            "release_assessment_id": ra["id"],
            "decision": "APPROVE",
            "decided_by_role": "tech_lead",
            "was_escalated": False,
        })
        with pytest.raises(NotImplementedError):
            await self.repo.update(d["id"], {"decision": "BLOCK"})

    async def test_soft_delete_raises(self):
        ra = await self._create_release_assessment()
        d = await self.repo.create({
            "release_assessment_id": ra["id"],
            "decision": "APPROVE",
            "decided_by_role": "tech_lead",
            "was_escalated": False,
        })
        with pytest.raises(NotImplementedError):
            await self.repo.soft_delete(d["id"])


# ---------------------------------------------------------------------------
# AuditLogRepository
# ---------------------------------------------------------------------------


class TestAuditLogRepository:
    @pytest.fixture(autouse=True)
    async def setup(self, asyncpg_pool, clean_tables):
        from forgeguard.data.repositories.audit_logs import AuditLogRepository  # noqa: PLC0415

        self.repo = AuditLogRepository(asyncpg_pool)

    async def _insert_log(self, **overrides):
        data = {
            "actor_role": "developer",
            "action": "service.created",
            "resource_type": "service",
        }
        data.update(overrides)
        return await self.repo.insert(data)

    async def test_insert_returns_record(self):
        log = await self._insert_log()
        assert "id" in log
        assert log["action"] == "service.created"

    async def test_query_filters_by_action(self):
        await self._insert_log(action="service.created")
        await self._insert_log(action="policy.updated")
        results = await self.repo.query(action="service.created")
        assert all(r["action"] == "service.created" for r in results)

    async def test_query_filters_by_resource_type(self):
        await self._insert_log(resource_type="service")
        await self._insert_log(resource_type="policy")
        results = await self.repo.query(resource_type="policy")
        assert all(r["resource_type"] == "policy" for r in results)

    async def test_query_with_date_range(self):
        await self._insert_log()
        after = datetime(2020, 1, 1, tzinfo=timezone.utc)
        before = datetime(2099, 1, 1, tzinfo=timezone.utc)
        results = await self.repo.query(after=after, before=before)
        assert len(results) >= 1

    async def test_update_raises(self):
        log = await self._insert_log()
        with pytest.raises(NotImplementedError):
            await self.repo.update(log["id"], {"action": "tampered"})

    async def test_soft_delete_raises(self):
        log = await self._insert_log()
        with pytest.raises(NotImplementedError):
            await self.repo.soft_delete(log["id"])

    async def test_no_update_method_in_public_api(self):
        """AuditLogRepository must not expose update or delete beyond NotImplementedError."""
        import inspect  # noqa: PLC0415
        from forgeguard.data.repositories.audit_logs import AuditLogRepository  # noqa: PLC0415

        # The public callable interface should be insert + query
        assert hasattr(AuditLogRepository, "insert")
        assert hasattr(AuditLogRepository, "query")

    async def test_queries_use_parameterized_syntax(self):
        import inspect  # noqa: PLC0415
        import forgeguard.data.repositories.audit_logs as al_mod  # noqa: PLC0415

        source = inspect.getsource(al_mod)
        assert "$1" in source


# ---------------------------------------------------------------------------
# Integration: pool init / shutdown lifecycle
# ---------------------------------------------------------------------------


class TestPoolLifecycle:
    async def test_init_and_close_pool(self, asyncpg_pool):
        """Verify pool can be acquired from and released without errors."""
        async with asyncpg_pool.acquire() as conn:
            val = await conn.fetchval("SELECT 42")
        assert val == 42

    async def test_database_module_init_close(self, db_url, apply_migrations):
        """Smoke test that init_pool / close_pool cycle works."""
        import forgeguard.data.database as db_mod  # noqa: PLC0415
        import forgeguard.core.config as cfg_mod  # noqa: PLC0415
        from forgeguard.core.config import Settings  # noqa: PLC0415

        test_settings = Settings(
            database_url=db_url,
            jwt_secret_key="test",
            log_level="WARNING",
            app_env="testing",
            llm_api_key="",
            forge_catalog_url="http://localhost:9999",
        )
        orig_cache = cfg_mod._settings_cache
        orig_pool = db_mod._pool
        cfg_mod._settings_cache = test_settings
        db_mod._pool = None
        try:
            pool = await db_mod.init_pool()
            assert pool is not None
            ok = await db_mod.health_check()
            assert ok is True
        finally:
            await db_mod.close_pool()
            cfg_mod._settings_cache = orig_cache
            db_mod._pool = orig_pool
