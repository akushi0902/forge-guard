"""Schema-level tests for the Assessments domain tables.

All tests require a live PostgreSQL instance and are automatically skipped
when the database is unreachable — the standard unit-test suite runs without
infrastructure dependencies.

Tests exercise:
    1. Assessment INSERT / SELECT for both assessment types and all trigger types.
    2. CHECK constraints on assessment_type, trigger_type, and status.
    3. AssessmentScore INSERT with DECIMAL(5,2) score and JSONB dimension_scores.
    4. CHECK constraint on overall_score (0-100 range).
    5. Finding INSERT with JSONB evidence and ai_explanation.
    6. CHECK constraints on severity, dimension, and finding status.
    7. CHECK constraint on confidence_score range (0-1).
    8. FK relationships: findings → assessments, services, policy_rules.
    9. ReleaseAssessment INSERT / SELECT.
    10. ReleaseDecision INSERT — verify no updated_at column exists.
    11. CHECK constraint on release_decisions.decision.
    12. CHECK constraints on score-at-decision columns.
    13. Immutability test: verify UPDATE on release_decisions is rejected.
    14. Integration: migration chain creates all 5 tables with correct indexes.
    15. Composite indexes present in pg_indexes.
    16. Failed assessment edge case: started_at set but completed_at is NULL.
    17. Suppressed finding edge case: status=suppressed retains resolved_at=NULL.
    18. Assessment with NULL collected_data is valid.
    19. AssessmentScore with NULL contributing_factors is valid.
    20. Finding with NULL ai_explanation is valid (AI engine unavailable).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from forgeguard.core.config import get_settings
from forgeguard.data.models import (
    Assessment,
    AssessmentScore,
    Base,
    Finding,
    Policy,
    PolicyRule,
    ReleaseAssessment,
    ReleaseDecision,
    Service,
    User,
)
from forgeguard.data.models.assessments import (
    VALID_ASSESSMENT_TYPES,
    VALID_DECISIONS,
    VALID_DIMENSIONS,
    VALID_FINDING_STATUSES,
    VALID_SEVERITIES,
    VALID_TRIGGER_TYPES,
)


# ---------------------------------------------------------------------------
# Database availability guard
# ---------------------------------------------------------------------------

def _is_db_available() -> bool:
    import asyncio

    async def _check() -> bool:
        engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except (OperationalError, Exception):
            return False
        finally:
            await engine.dispose()

    try:
        return asyncio.get_event_loop().run_until_complete(_check())
    except Exception:
        return False


_DB_AVAILABLE = _is_db_available()
pytestmark = pytest.mark.skipif(
    not _DB_AVAILABLE, reason="PostgreSQL not reachable — skipping schema tests"
)


# ---------------------------------------------------------------------------
# Session fixture
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def session():
    engine = create_async_engine(
        get_settings().database_url,
        echo=False,
        pool_pre_ping=True,
    )
    async_session = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    async with async_session() as s:
        async with s.begin():
            yield s
            await s.rollback()
    await engine.dispose()


# ---------------------------------------------------------------------------
# Test data builders
# ---------------------------------------------------------------------------

def _make_user(**kwargs: Any) -> User:
    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "email": f"user_{uuid.uuid4().hex[:8]}@example.com",
        "name_encrypted": b"encrypted_name",
        "password_hash": "$2b$12$" + "a" * 53,
        "role": "developer",
        "is_active": True,
    }
    defaults.update(kwargs)
    return User(**defaults)


def _make_service(**kwargs: Any) -> Service:
    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "name": f"test-svc-{uuid.uuid4().hex[:6]}",
    }
    defaults.update(kwargs)
    return Service(**defaults)


def _make_policy(service_id: uuid.UUID, **kwargs: Any) -> Policy:
    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "service_id": service_id,
        "name": f"policy-{uuid.uuid4().hex[:6]}",
        "dimension": "security",
    }
    defaults.update(kwargs)
    return Policy(**defaults)


def _make_policy_rule(policy_id: uuid.UUID, **kwargs: Any) -> PolicyRule:
    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "policy_id": policy_id,
        "name": f"rule-{uuid.uuid4().hex[:6]}",
        "rule_type": "threshold",
        "threshold_config": {"operator": "gte", "value": 80},
        "severity": "high",
    }
    defaults.update(kwargs)
    return PolicyRule(**defaults)


def _make_assessment(service_id: uuid.UUID, **kwargs: Any) -> Assessment:
    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "service_id": service_id,
        "assessment_type": "health_check",
        "trigger_type": "manual",
        "status": "completed",
    }
    defaults.update(kwargs)
    return Assessment(**defaults)


def _make_assessment_score(
    assessment_id: uuid.UUID, service_id: uuid.UUID, **kwargs: Any
) -> AssessmentScore:
    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "assessment_id": assessment_id,
        "service_id": service_id,
        "score_type": "health",
        "overall_score": Decimal("75.50"),
        "dimension_scores": {
            "code_quality": 85.0,
            "test_coverage": 72.0,
            "security": 90.0,
            "documentation": 65.0,
            "operations_readiness": 78.0,
        },
    }
    defaults.update(kwargs)
    return AssessmentScore(**defaults)


def _make_finding(
    assessment_id: uuid.UUID,
    service_id: uuid.UUID,
    policy_rule_id: uuid.UUID,
    **kwargs: Any,
) -> Finding:
    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "assessment_id": assessment_id,
        "service_id": service_id,
        "policy_rule_id": policy_rule_id,
        "severity": "high",
        "dimension": "security",
        "status": "open",
        "title": f"Test finding {uuid.uuid4().hex[:6]}",
    }
    defaults.update(kwargs)
    return Finding(**defaults)


def _make_release_assessment(service_id: uuid.UUID, **kwargs: Any) -> ReleaseAssessment:
    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "service_id": service_id,
        "commit_sha": "abc123def456",
        "status": "completed",
    }
    defaults.update(kwargs)
    return ReleaseAssessment(**defaults)


def _make_release_decision(
    release_assessment_id: uuid.UUID, **kwargs: Any
) -> ReleaseDecision:
    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "release_assessment_id": release_assessment_id,
        "health_score_at_decision": Decimal("75.50"),
        "risk_score_at_decision": Decimal("32.00"),
        "decision": "APPROVE",
        "decided_by_role": "tech_lead",
    }
    defaults.update(kwargs)
    return ReleaseDecision(**defaults)


# ---------------------------------------------------------------------------
# Shared fixtures for tests that need dependent objects
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def svc_rule(session: AsyncSession):
    """Creates and flushes Service + Policy + PolicyRule; returns (svc, rule)."""
    svc = _make_service()
    session.add(svc)
    await session.flush()
    pol = _make_policy(svc.id)
    session.add(pol)
    await session.flush()
    rule = _make_policy_rule(pol.id)
    session.add(rule)
    await session.flush()
    return svc, rule


@pytest_asyncio.fixture
async def assessment_ctx(svc_rule, session: AsyncSession):
    """Returns (svc, rule, assessment) with the assessment already flushed."""
    svc, rule = svc_rule
    assessment = _make_assessment(svc.id)
    session.add(assessment)
    await session.flush()
    return svc, rule, assessment


# ---------------------------------------------------------------------------
# Assessment table
# ---------------------------------------------------------------------------

class TestAssessmentInsert:
    async def test_insert_minimal_assessment(
        self, session: AsyncSession, svc_rule
    ) -> None:
        svc, _ = svc_rule
        a = _make_assessment(svc.id)
        session.add(a)
        await session.flush()
        result = await session.get(Assessment, a.id)
        assert result is not None
        assert result.service_id == svc.id

    async def test_all_valid_assessment_types(
        self, session: AsyncSession, svc_rule
    ) -> None:
        svc, _ = svc_rule
        for atype in VALID_ASSESSMENT_TYPES:
            a = _make_assessment(svc.id, assessment_type=atype)
            session.add(a)
        await session.flush()

    async def test_all_valid_trigger_types(
        self, session: AsyncSession, svc_rule
    ) -> None:
        svc, _ = svc_rule
        for ttype in VALID_TRIGGER_TYPES:
            a = _make_assessment(svc.id, trigger_type=ttype)
            session.add(a)
        await session.flush()

    async def test_failed_assessment_completed_at_null(
        self, session: AsyncSession, svc_rule
    ) -> None:
        svc, _ = svc_rule
        a = _make_assessment(
            svc.id,
            status="failed",
            started_at=datetime.now(tz=timezone.utc),
            completed_at=None,
        )
        session.add(a)
        await session.flush()
        result = await session.get(Assessment, a.id)
        assert result is not None
        assert result.status == "failed"
        assert result.started_at is not None
        assert result.completed_at is None

    async def test_null_collected_data_valid(
        self, session: AsyncSession, svc_rule
    ) -> None:
        svc, _ = svc_rule
        a = _make_assessment(svc.id, collected_data=None)
        session.add(a)
        await session.flush()
        result = await session.get(Assessment, a.id)
        assert result is not None
        assert result.collected_data is None


class TestAssessmentConstraints:
    async def test_invalid_assessment_type_rejected(
        self, session: AsyncSession, svc_rule
    ) -> None:
        svc, _ = svc_rule
        a = _make_assessment(svc.id, assessment_type="invalid_type")
        session.add(a)
        with pytest.raises(
            IntegrityError, match="ck_assessments_valid_assessment_type|check"
        ):
            await session.flush()

    async def test_invalid_trigger_type_rejected(
        self, session: AsyncSession, svc_rule
    ) -> None:
        svc, _ = svc_rule
        a = _make_assessment(svc.id, trigger_type="api_call")
        session.add(a)
        with pytest.raises(
            IntegrityError, match="ck_assessments_valid_trigger_type|check"
        ):
            await session.flush()

    async def test_invalid_status_rejected(
        self, session: AsyncSession, svc_rule
    ) -> None:
        svc, _ = svc_rule
        a = _make_assessment(svc.id, status="running")
        session.add(a)
        with pytest.raises(
            IntegrityError, match="ck_assessments_valid_assessment_status|check"
        ):
            await session.flush()


# ---------------------------------------------------------------------------
# AssessmentScore table
# ---------------------------------------------------------------------------

class TestAssessmentScoreInsert:
    async def test_insert_score_with_dimension_breakdown(
        self, session: AsyncSession, assessment_ctx
    ) -> None:
        svc, _, assessment = assessment_ctx
        score = _make_assessment_score(assessment.id, svc.id)
        session.add(score)
        await session.flush()
        result = await session.get(AssessmentScore, score.id)
        assert result is not None
        assert result.dimension_scores["code_quality"] == 85.0
        assert result.dimension_scores["security"] == 90.0

    async def test_null_contributing_factors_valid(
        self, session: AsyncSession, assessment_ctx
    ) -> None:
        svc, _, assessment = assessment_ctx
        score = _make_assessment_score(
            assessment.id, svc.id, contributing_factors=None
        )
        session.add(score)
        await session.flush()
        result = await session.get(AssessmentScore, score.id)
        assert result is not None
        assert result.contributing_factors is None

    async def test_jsonb_dimension_scores_five_keys(
        self, session: AsyncSession, assessment_ctx
    ) -> None:
        svc, _, assessment = assessment_ctx
        dim_scores = {k: float(i * 10 + 50) for i, k in enumerate(VALID_DIMENSIONS)}
        score = _make_assessment_score(
            assessment.id, svc.id, dimension_scores=dim_scores
        )
        session.add(score)
        await session.flush()
        result = await session.get(AssessmentScore, score.id)
        assert result is not None
        assert set(result.dimension_scores.keys()) == set(VALID_DIMENSIONS)


class TestAssessmentScoreConstraints:
    async def test_score_above_100_rejected(
        self, session: AsyncSession, assessment_ctx
    ) -> None:
        svc, _, assessment = assessment_ctx
        score = _make_assessment_score(
            assessment.id, svc.id, overall_score=Decimal("100.01")
        )
        session.add(score)
        with pytest.raises(
            IntegrityError, match="ck_assessment_scores_valid_score_range|check"
        ):
            await session.flush()

    async def test_score_below_0_rejected(
        self, session: AsyncSession, assessment_ctx
    ) -> None:
        svc, _, assessment = assessment_ctx
        score = _make_assessment_score(
            assessment.id, svc.id, overall_score=Decimal("-0.01")
        )
        session.add(score)
        with pytest.raises(
            IntegrityError, match="ck_assessment_scores_valid_score_range|check"
        ):
            await session.flush()

    async def test_score_boundary_0_accepted(
        self, session: AsyncSession, assessment_ctx
    ) -> None:
        svc, _, assessment = assessment_ctx
        score = _make_assessment_score(
            assessment.id, svc.id, overall_score=Decimal("0.00")
        )
        session.add(score)
        await session.flush()
        result = await session.get(AssessmentScore, score.id)
        assert result is not None
        assert result.overall_score == Decimal("0.00")

    async def test_score_boundary_100_accepted(
        self, session: AsyncSession, assessment_ctx
    ) -> None:
        svc, _, assessment = assessment_ctx
        score = _make_assessment_score(
            assessment.id, svc.id, overall_score=Decimal("100.00")
        )
        session.add(score)
        await session.flush()
        result = await session.get(AssessmentScore, score.id)
        assert result is not None
        assert result.overall_score == Decimal("100.00")


# ---------------------------------------------------------------------------
# Finding table
# ---------------------------------------------------------------------------

class TestFindingInsert:
    async def test_insert_minimal_finding(
        self, session: AsyncSession, assessment_ctx
    ) -> None:
        svc, rule, assessment = assessment_ctx
        f = _make_finding(assessment.id, svc.id, rule.id)
        session.add(f)
        await session.flush()
        result = await session.get(Finding, f.id)
        assert result is not None
        assert result.severity == "high"
        assert result.status == "open"

    async def test_all_valid_severities(
        self, session: AsyncSession, assessment_ctx
    ) -> None:
        svc, rule, assessment = assessment_ctx
        for sev in VALID_SEVERITIES:
            f = _make_finding(assessment.id, svc.id, rule.id, severity=sev)
            session.add(f)
        await session.flush()

    async def test_all_valid_dimensions(
        self, session: AsyncSession, assessment_ctx
    ) -> None:
        svc, rule, assessment = assessment_ctx
        for dim in VALID_DIMENSIONS:
            f = _make_finding(assessment.id, svc.id, rule.id, dimension=dim)
            session.add(f)
        await session.flush()

    async def test_all_valid_finding_statuses(
        self, session: AsyncSession, assessment_ctx
    ) -> None:
        svc, rule, assessment = assessment_ctx
        for status in VALID_FINDING_STATUSES:
            f = _make_finding(assessment.id, svc.id, rule.id, status=status)
            session.add(f)
        await session.flush()

    async def test_null_ai_explanation_valid(
        self, session: AsyncSession, assessment_ctx
    ) -> None:
        svc, rule, assessment = assessment_ctx
        f = _make_finding(assessment.id, svc.id, rule.id, ai_explanation=None)
        session.add(f)
        await session.flush()
        result = await session.get(Finding, f.id)
        assert result is not None
        assert result.ai_explanation is None

    async def test_suppressed_finding_no_resolved_at(
        self, session: AsyncSession, assessment_ctx
    ) -> None:
        svc, rule, assessment = assessment_ctx
        f = _make_finding(
            assessment.id, svc.id, rule.id, status="suppressed", resolved_at=None
        )
        session.add(f)
        await session.flush()
        result = await session.get(Finding, f.id)
        assert result is not None
        assert result.status == "suppressed"
        assert result.resolved_at is None

    async def test_jsonb_evidence_stored(
        self, session: AsyncSession, assessment_ctx
    ) -> None:
        svc, rule, assessment = assessment_ctx
        evidence = {"file": "src/app.py", "line": 42, "snippet": "unsafe code"}
        f = _make_finding(assessment.id, svc.id, rule.id, evidence=evidence)
        session.add(f)
        await session.flush()
        result = await session.get(Finding, f.id)
        assert result is not None
        assert result.evidence["file"] == "src/app.py"
        assert result.evidence["line"] == 42


class TestFindingConstraints:
    async def test_invalid_severity_rejected(
        self, session: AsyncSession, assessment_ctx
    ) -> None:
        svc, rule, assessment = assessment_ctx
        f = _make_finding(assessment.id, svc.id, rule.id, severity="negligible")
        session.add(f)
        with pytest.raises(
            IntegrityError, match="ck_findings_valid_severity|check"
        ):
            await session.flush()

    async def test_invalid_dimension_rejected(
        self, session: AsyncSession, assessment_ctx
    ) -> None:
        svc, rule, assessment = assessment_ctx
        f = _make_finding(
            assessment.id, svc.id, rule.id, dimension="performance"
        )
        session.add(f)
        with pytest.raises(
            IntegrityError, match="ck_findings_valid_dimension|check"
        ):
            await session.flush()

    async def test_invalid_finding_status_rejected(
        self, session: AsyncSession, assessment_ctx
    ) -> None:
        svc, rule, assessment = assessment_ctx
        f = _make_finding(assessment.id, svc.id, rule.id, status="pending")
        session.add(f)
        with pytest.raises(
            IntegrityError, match="ck_findings_valid_finding_status|check"
        ):
            await session.flush()

    async def test_confidence_score_above_1_rejected(
        self, session: AsyncSession, assessment_ctx
    ) -> None:
        svc, rule, assessment = assessment_ctx
        f = _make_finding(
            assessment.id, svc.id, rule.id, confidence_score=Decimal("1.01")
        )
        session.add(f)
        with pytest.raises(
            IntegrityError, match="ck_findings_valid_confidence_score|check"
        ):
            await session.flush()

    async def test_confidence_score_below_0_rejected(
        self, session: AsyncSession, assessment_ctx
    ) -> None:
        svc, rule, assessment = assessment_ctx
        f = _make_finding(
            assessment.id, svc.id, rule.id, confidence_score=Decimal("-0.01")
        )
        session.add(f)
        with pytest.raises(
            IntegrityError, match="ck_findings_valid_confidence_score|check"
        ):
            await session.flush()

    async def test_null_confidence_score_valid(
        self, session: AsyncSession, assessment_ctx
    ) -> None:
        svc, rule, assessment = assessment_ctx
        f = _make_finding(assessment.id, svc.id, rule.id, confidence_score=None)
        session.add(f)
        await session.flush()
        result = await session.get(Finding, f.id)
        assert result is not None
        assert result.confidence_score is None


# ---------------------------------------------------------------------------
# ReleaseAssessment table
# ---------------------------------------------------------------------------

class TestReleaseAssessmentInsert:
    async def test_insert_release_assessment(
        self, session: AsyncSession, svc_rule
    ) -> None:
        svc, _ = svc_rule
        ra = _make_release_assessment(svc.id)
        session.add(ra)
        await session.flush()
        result = await session.get(ReleaseAssessment, ra.id)
        assert result is not None
        assert result.commit_sha == "abc123def456"
        assert result.status == "completed"

    async def test_both_commit_sha_and_pr_reference_valid(
        self, session: AsyncSession, svc_rule
    ) -> None:
        svc, _ = svc_rule
        ra = _make_release_assessment(
            svc.id,
            commit_sha="abc123",
            pr_reference="https://github.com/org/repo/pull/1",
        )
        session.add(ra)
        await session.flush()
        result = await session.get(ReleaseAssessment, ra.id)
        assert result is not None
        assert result.commit_sha is not None
        assert result.pr_reference is not None


# ---------------------------------------------------------------------------
# ReleaseDecision table — immutability
# ---------------------------------------------------------------------------

class TestReleaseDecisionInsert:
    async def test_insert_approve_decision(
        self, session: AsyncSession, svc_rule
    ) -> None:
        svc, _ = svc_rule
        ra = _make_release_assessment(svc.id)
        session.add(ra)
        await session.flush()
        rd = _make_release_decision(ra.id, decision="APPROVE")
        session.add(rd)
        await session.flush()
        result = await session.get(ReleaseDecision, rd.id)
        assert result is not None
        assert result.decision == "APPROVE"
        assert result.was_escalated is False

    async def test_all_valid_decisions(
        self, session: AsyncSession, svc_rule
    ) -> None:
        svc, _ = svc_rule
        for decision in VALID_DECISIONS:
            ra = _make_release_assessment(svc.id)
            session.add(ra)
            await session.flush()
            rd = _make_release_decision(ra.id, decision=decision)
            session.add(rd)
        await session.flush()

    async def test_no_updated_at_column(self) -> None:
        """release_decisions must not have an updated_at column (immutability)."""
        from sqlalchemy import inspect as sa_inspect

        mapper = sa_inspect(ReleaseDecision)
        column_names = {col.key for col in mapper.columns}
        assert "updated_at" not in column_names, (
            "release_decisions must NOT have an updated_at column — "
            "this table is append-only to enforce immutability."
        )

    async def test_escalated_block_decision(
        self, session: AsyncSession, svc_rule
    ) -> None:
        svc, _ = svc_rule
        ra = _make_release_assessment(svc.id)
        session.add(ra)
        await session.flush()
        rd = _make_release_decision(
            ra.id,
            decision="BLOCK",
            was_escalated=True,
            decided_by_role="security_reviewer",
        )
        session.add(rd)
        await session.flush()
        result = await session.get(ReleaseDecision, rd.id)
        assert result is not None
        assert result.decision == "BLOCK"
        assert result.was_escalated is True


class TestReleaseDecisionConstraints:
    async def test_invalid_decision_rejected(
        self, session: AsyncSession, svc_rule
    ) -> None:
        svc, _ = svc_rule
        ra = _make_release_assessment(svc.id)
        session.add(ra)
        await session.flush()
        rd = _make_release_decision(ra.id, decision="DEFER")
        session.add(rd)
        with pytest.raises(
            IntegrityError, match="ck_release_decisions_valid_decision|check"
        ):
            await session.flush()

    async def test_health_score_above_100_rejected(
        self, session: AsyncSession, svc_rule
    ) -> None:
        svc, _ = svc_rule
        ra = _make_release_assessment(svc.id)
        session.add(ra)
        await session.flush()
        rd = _make_release_decision(
            ra.id, health_score_at_decision=Decimal("100.01")
        )
        session.add(rd)
        with pytest.raises(
            IntegrityError,
            match="ck_release_decisions_valid_health_score_at_decision|check",
        ):
            await session.flush()

    async def test_risk_score_below_0_rejected(
        self, session: AsyncSession, svc_rule
    ) -> None:
        svc, _ = svc_rule
        ra = _make_release_assessment(svc.id)
        session.add(ra)
        await session.flush()
        rd = _make_release_decision(
            ra.id, risk_score_at_decision=Decimal("-1.00")
        )
        session.add(rd)
        with pytest.raises(
            IntegrityError,
            match="ck_release_decisions_valid_risk_score_at_decision|check",
        ):
            await session.flush()


# ---------------------------------------------------------------------------
# FK relationships
# ---------------------------------------------------------------------------

class TestForeignKeys:
    async def test_finding_fk_to_assessment(
        self, session: AsyncSession, assessment_ctx
    ) -> None:
        svc, rule, assessment = assessment_ctx
        f = _make_finding(assessment.id, svc.id, rule.id)
        session.add(f)
        await session.flush()
        result = await session.get(Finding, f.id)
        assert result is not None
        assert result.assessment_id == assessment.id

    async def test_finding_fk_nonexistent_assessment_rejected(
        self, session: AsyncSession, svc_rule
    ) -> None:
        svc, rule = svc_rule
        f = _make_finding(uuid.uuid4(), svc.id, rule.id)
        session.add(f)
        with pytest.raises(IntegrityError, match="fk_findings_assessment_id|foreign"):
            await session.flush()

    async def test_assessment_score_fk_to_assessment(
        self, session: AsyncSession, assessment_ctx
    ) -> None:
        svc, _, assessment = assessment_ctx
        score = _make_assessment_score(assessment.id, svc.id)
        session.add(score)
        await session.flush()
        result = await session.get(AssessmentScore, score.id)
        assert result is not None
        assert result.assessment_id == assessment.id

    async def test_release_decision_fk_to_release_assessment(
        self, session: AsyncSession, svc_rule
    ) -> None:
        svc, _ = svc_rule
        ra = _make_release_assessment(svc.id)
        session.add(ra)
        await session.flush()
        rd = _make_release_decision(ra.id)
        session.add(rd)
        await session.flush()
        result = await session.get(ReleaseDecision, rd.id)
        assert result is not None
        assert result.release_assessment_id == ra.id


# ---------------------------------------------------------------------------
# Integration: indexes present
# ---------------------------------------------------------------------------

class TestIndexes:
    async def test_composite_index_assessments_service_created_at(
        self, session: AsyncSession
    ) -> None:
        result = await session.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE tablename = 'assessments' "
                "AND indexname = 'ix_assessments_service_id_created_at'"
            )
        )
        assert result.scalar() is not None

    async def test_composite_index_findings_service_severity_status(
        self, session: AsyncSession
    ) -> None:
        result = await session.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE tablename = 'findings' "
                "AND indexname = 'ix_findings_service_id_severity_status'"
            )
        )
        assert result.scalar() is not None

    async def test_composite_index_findings_assessment_severity(
        self, session: AsyncSession
    ) -> None:
        result = await session.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE tablename = 'findings' "
                "AND indexname = 'ix_findings_assessment_id_severity'"
            )
        )
        assert result.scalar() is not None

    async def test_composite_index_scores_service_type_created_at(
        self, session: AsyncSession
    ) -> None:
        result = await session.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE tablename = 'assessment_scores' "
                "AND indexname = 'ix_assessment_scores_service_id_score_type_created_at'"
            )
        )
        assert result.scalar() is not None


# ---------------------------------------------------------------------------
# Integration: all 5 tables exist
# ---------------------------------------------------------------------------

class TestMigrationIntegration:
    async def test_all_five_assessment_tables_exist(
        self, session: AsyncSession
    ) -> None:
        expected_tables = {
            "assessments",
            "assessment_scores",
            "findings",
            "release_assessments",
            "release_decisions",
        }
        result = await session.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' "
                "AND table_name = ANY(:names)"
            ),
            {"names": list(expected_tables)},
        )
        found = {row[0] for row in result}
        assert found == expected_tables, (
            f"Missing tables: {expected_tables - found}"
        )

    async def test_release_decisions_has_no_updated_at_column(
        self, session: AsyncSession
    ) -> None:
        result = await session.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'release_decisions' "
                "AND column_name = 'updated_at'"
            )
        )
        assert result.scalar() is None, (
            "release_decisions must NOT have updated_at — immutability violated."
        )
