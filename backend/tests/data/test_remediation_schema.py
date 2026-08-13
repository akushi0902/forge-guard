"""Schema-level tests for the Remediation domain tables.

All tests require a live PostgreSQL instance and are automatically skipped
when the database is unreachable — the standard unit-test suite runs without
infrastructure dependencies.

Tests exercise:
    1. RemediationRecommendation INSERT with each valid source type.
    2. CHECK constraint on source rejects invalid values.
    3. CHECK constraint on confidence_score rejects values outside 0-1.
    4. confidence_score boundary values 0.00 and 1.00 accepted.
    5. NULL confidence_score is valid (manual recommendations).
    6. Multiple recommendations for a single finding (no unique constraint).
    7. CASCADE: deleting a finding removes its recommendations.
    8. FindingException INSERT with each valid status.
    9. CHECK constraint on exception status rejects invalid values.
    10. NOT NULL on justification rejects empty or missing value.
    11. NOT NULL on expires_at rejects NULL.
    12. decided_by NULL with status=requested is valid (not yet reviewed).
    13. RESTRICT FK: cannot delete a finding that has exceptions.
    14. Index on exceptions(expires_at) is present in pg_indexes.
    15. Index on exceptions(status) is present in pg_indexes.
    16. Index on remediation_recommendations(finding_id) is present.
    17. Integration: both tables exist in information_schema.tables.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from forgeguard.core.config import get_settings
from forgeguard.data.models import (
    Assessment,
    Base,
    Finding,
    FindingException,
    Policy,
    PolicyRule,
    RemediationRecommendation,
    Service,
)
from forgeguard.data.models.remediation import (
    VALID_EXCEPTION_STATUSES,
    VALID_RECOMMENDATION_SOURCES,
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

def _make_service(**kwargs: Any) -> Service:
    return Service(id=uuid.uuid4(), name=f"svc-{uuid.uuid4().hex[:6]}", **kwargs)


def _make_policy(service_id: uuid.UUID, **kwargs: Any) -> Policy:
    return Policy(
        id=uuid.uuid4(),
        service_id=service_id,
        name=f"pol-{uuid.uuid4().hex[:6]}",
        dimension="security",
        **kwargs,
    )


def _make_policy_rule(policy_id: uuid.UUID, **kwargs: Any) -> PolicyRule:
    return PolicyRule(
        id=uuid.uuid4(),
        policy_id=policy_id,
        name=f"rule-{uuid.uuid4().hex[:6]}",
        rule_type="threshold",
        threshold_config={"operator": "gte", "value": 80},
        severity="high",
        **kwargs,
    )


def _make_assessment(service_id: uuid.UUID, **kwargs: Any) -> Assessment:
    return Assessment(
        id=uuid.uuid4(),
        service_id=service_id,
        assessment_type="health_check",
        trigger_type="manual",
        status="completed",
        **kwargs,
    )


def _make_finding(
    assessment_id: uuid.UUID,
    service_id: uuid.UUID,
    policy_rule_id: uuid.UUID,
    **kwargs: Any,
) -> Finding:
    return Finding(
        id=uuid.uuid4(),
        assessment_id=assessment_id,
        service_id=service_id,
        policy_rule_id=policy_rule_id,
        severity="high",
        dimension="security",
        status="open",
        title=f"finding-{uuid.uuid4().hex[:6]}",
        **kwargs,
    )


def _make_recommendation(finding_id: uuid.UUID, **kwargs: Any) -> RemediationRecommendation:
    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "finding_id": finding_id,
        "recommendation_text": "Fix the issue by applying the recommended changes.",
        "source": "ai_generated",
        "confidence_score": Decimal("0.85"),
    }
    defaults.update(kwargs)
    return RemediationRecommendation(**defaults)


def _make_exception(finding_id: uuid.UUID, **kwargs: Any) -> FindingException:
    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "finding_id": finding_id,
        "justification": "Temporary exception while fix is planned.",
        "status": "requested",
        "expires_at": datetime.now(tz=timezone.utc) + timedelta(days=30),
    }
    defaults.update(kwargs)
    return FindingException(**defaults)


# ---------------------------------------------------------------------------
# Shared fixture: finding + required ancestors
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def finding_ctx(session: AsyncSession):
    """Returns (svc, rule, assessment, finding) — all flushed to DB."""
    svc = _make_service()
    session.add(svc)
    await session.flush()
    pol = _make_policy(svc.id)
    session.add(pol)
    await session.flush()
    rule = _make_policy_rule(pol.id)
    session.add(rule)
    await session.flush()
    assessment = _make_assessment(svc.id)
    session.add(assessment)
    await session.flush()
    finding = _make_finding(assessment.id, svc.id, rule.id)
    session.add(finding)
    await session.flush()
    return svc, rule, assessment, finding


# ---------------------------------------------------------------------------
# RemediationRecommendation — valid inserts
# ---------------------------------------------------------------------------

class TestRemediationRecommendationInsert:
    async def test_insert_ai_generated_recommendation(
        self, session: AsyncSession, finding_ctx
    ) -> None:
        _, _, _, finding = finding_ctx
        rec = _make_recommendation(finding.id, source="ai_generated")
        session.add(rec)
        await session.flush()
        result = await session.get(RemediationRecommendation, rec.id)
        assert result is not None
        assert result.source == "ai_generated"
        assert result.finding_id == finding.id

    async def test_all_valid_sources(
        self, session: AsyncSession, finding_ctx
    ) -> None:
        _, _, _, finding = finding_ctx
        for src in VALID_RECOMMENDATION_SOURCES:
            rec = _make_recommendation(finding.id, source=src)
            session.add(rec)
        await session.flush()

    async def test_null_confidence_score_valid(
        self, session: AsyncSession, finding_ctx
    ) -> None:
        _, _, _, finding = finding_ctx
        rec = _make_recommendation(finding.id, confidence_score=None, source="manual")
        session.add(rec)
        await session.flush()
        result = await session.get(RemediationRecommendation, rec.id)
        assert result is not None
        assert result.confidence_score is None

    async def test_null_implementation_guide_valid(
        self, session: AsyncSession, finding_ctx
    ) -> None:
        _, _, _, finding = finding_ctx
        rec = _make_recommendation(
            finding.id, source="template_fallback", implementation_guide=None
        )
        session.add(rec)
        await session.flush()
        result = await session.get(RemediationRecommendation, rec.id)
        assert result is not None
        assert result.implementation_guide is None

    async def test_multiple_recommendations_for_one_finding(
        self, session: AsyncSession, finding_ctx
    ) -> None:
        _, _, _, finding = finding_ctx
        for src in VALID_RECOMMENDATION_SOURCES:
            rec = _make_recommendation(finding.id, source=src)
            session.add(rec)
        await session.flush()

    async def test_confidence_score_boundary_0_00(
        self, session: AsyncSession, finding_ctx
    ) -> None:
        _, _, _, finding = finding_ctx
        rec = _make_recommendation(finding.id, confidence_score=Decimal("0.00"))
        session.add(rec)
        await session.flush()
        result = await session.get(RemediationRecommendation, rec.id)
        assert result is not None
        assert result.confidence_score == Decimal("0.00")

    async def test_confidence_score_boundary_1_00(
        self, session: AsyncSession, finding_ctx
    ) -> None:
        _, _, _, finding = finding_ctx
        rec = _make_recommendation(finding.id, confidence_score=Decimal("1.00"))
        session.add(rec)
        await session.flush()
        result = await session.get(RemediationRecommendation, rec.id)
        assert result is not None
        assert result.confidence_score == Decimal("1.00")


# ---------------------------------------------------------------------------
# RemediationRecommendation — CHECK constraint violations
# ---------------------------------------------------------------------------

class TestRemediationRecommendationConstraints:
    async def test_invalid_source_rejected(
        self, session: AsyncSession, finding_ctx
    ) -> None:
        _, _, _, finding = finding_ctx
        rec = _make_recommendation(finding.id, source="llm_output")
        session.add(rec)
        with pytest.raises(
            IntegrityError,
            match="ck_remediation_recommendations_valid_source|check",
        ):
            await session.flush()

    async def test_confidence_score_above_1_rejected(
        self, session: AsyncSession, finding_ctx
    ) -> None:
        _, _, _, finding = finding_ctx
        rec = _make_recommendation(finding.id, confidence_score=Decimal("1.01"))
        session.add(rec)
        with pytest.raises(
            IntegrityError,
            match="ck_remediation_recommendations_valid_confidence_score|check",
        ):
            await session.flush()

    async def test_confidence_score_below_0_rejected(
        self, session: AsyncSession, finding_ctx
    ) -> None:
        _, _, _, finding = finding_ctx
        rec = _make_recommendation(finding.id, confidence_score=Decimal("-0.01"))
        session.add(rec)
        with pytest.raises(
            IntegrityError,
            match="ck_remediation_recommendations_valid_confidence_score|check",
        ):
            await session.flush()

    async def test_fk_nonexistent_finding_rejected(
        self, session: AsyncSession
    ) -> None:
        rec = _make_recommendation(uuid.uuid4())
        session.add(rec)
        with pytest.raises(
            IntegrityError,
            match="fk_remediation_recommendations_finding_id|foreign",
        ):
            await session.flush()


# ---------------------------------------------------------------------------
# FindingException — valid inserts
# ---------------------------------------------------------------------------

class TestFindingExceptionInsert:
    async def test_insert_requested_exception(
        self, session: AsyncSession, finding_ctx
    ) -> None:
        _, _, _, finding = finding_ctx
        exc = _make_exception(finding.id)
        session.add(exc)
        await session.flush()
        result = await session.get(FindingException, exc.id)
        assert result is not None
        assert result.status == "requested"
        assert result.decided_by is None
        assert result.decided_at is None

    async def test_all_valid_statuses(
        self, session: AsyncSession, finding_ctx
    ) -> None:
        _, _, _, finding = finding_ctx
        for status in VALID_EXCEPTION_STATUSES:
            exc = _make_exception(finding.id, status=status)
            session.add(exc)
        await session.flush()

    async def test_decided_by_null_with_requested_status_valid(
        self, session: AsyncSession, finding_ctx
    ) -> None:
        _, _, _, finding = finding_ctx
        exc = _make_exception(finding.id, status="requested", decided_by=None)
        session.add(exc)
        await session.flush()
        result = await session.get(FindingException, exc.id)
        assert result is not None
        assert result.decided_by is None

    async def test_null_decision_comment_valid(
        self, session: AsyncSession, finding_ctx
    ) -> None:
        _, _, _, finding = finding_ctx
        exc = _make_exception(finding.id, decision_comment=None)
        session.add(exc)
        await session.flush()
        result = await session.get(FindingException, exc.id)
        assert result is not None
        assert result.decision_comment is None

    async def test_expires_at_in_past_valid(
        self, session: AsyncSession, finding_ctx
    ) -> None:
        _, _, _, finding = finding_ctx
        exc = _make_exception(
            finding.id,
            status="expired",
            expires_at=datetime.now(tz=timezone.utc) - timedelta(days=1),
        )
        session.add(exc)
        await session.flush()
        result = await session.get(FindingException, exc.id)
        assert result is not None
        assert result.status == "expired"


# ---------------------------------------------------------------------------
# FindingException — CHECK and NOT NULL constraint violations
# ---------------------------------------------------------------------------

class TestFindingExceptionConstraints:
    async def test_invalid_status_rejected(
        self, session: AsyncSession, finding_ctx
    ) -> None:
        _, _, _, finding = finding_ctx
        exc = _make_exception(finding.id, status="pending")
        session.add(exc)
        with pytest.raises(
            IntegrityError,
            match="ck_exceptions_valid_exception_status|check",
        ):
            await session.flush()

    async def test_null_expires_at_rejected(
        self, session: AsyncSession, finding_ctx
    ) -> None:
        _, _, _, finding = finding_ctx
        # Build dict without expires_at so the column is absent entirely.
        exc = FindingException(
            id=uuid.uuid4(),
            finding_id=finding.id,
            justification="Test justification",
            status="requested",
            expires_at=None,  # type: ignore[arg-type]
        )
        session.add(exc)
        with pytest.raises(IntegrityError, match="null|not.null|violates"):
            await session.flush()

    async def test_fk_nonexistent_finding_rejected(
        self, session: AsyncSession
    ) -> None:
        exc = _make_exception(uuid.uuid4())
        session.add(exc)
        with pytest.raises(
            IntegrityError,
            match="fk_exceptions_finding_id|foreign",
        ):
            await session.flush()


# ---------------------------------------------------------------------------
# FK cascade / restrict behaviour
# ---------------------------------------------------------------------------

class TestCascadeAndRestrictBehavior:
    async def test_cascade_deletes_recommendation_with_finding(
        self, session: AsyncSession, finding_ctx
    ) -> None:
        _, _, _, finding = finding_ctx
        rec = _make_recommendation(finding.id)
        session.add(rec)
        await session.flush()
        rec_id = rec.id

        # Delete the finding — the recommendation should cascade-delete.
        await session.delete(finding)
        await session.flush()

        result = await session.get(RemediationRecommendation, rec_id)
        assert result is None, "Recommendation should have been cascade-deleted."

    async def test_restrict_prevents_finding_deletion_with_exception(
        self, session: AsyncSession, finding_ctx
    ) -> None:
        _, _, _, finding = finding_ctx
        exc = _make_exception(finding.id)
        session.add(exc)
        await session.flush()

        await session.delete(finding)
        with pytest.raises(IntegrityError, match="fk_exceptions_finding_id|foreign|restrict"):
            await session.flush()


# ---------------------------------------------------------------------------
# Indexes present in pg_indexes
# ---------------------------------------------------------------------------

class TestIndexes:
    async def test_index_recommendations_finding_id(
        self, session: AsyncSession
    ) -> None:
        result = await session.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE tablename = 'remediation_recommendations' "
                "AND indexname = 'ix_remediation_recommendations_finding_id'"
            )
        )
        assert result.scalar() is not None

    async def test_index_exceptions_status(self, session: AsyncSession) -> None:
        result = await session.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE tablename = 'exceptions' "
                "AND indexname = 'ix_exceptions_status'"
            )
        )
        assert result.scalar() is not None

    async def test_index_exceptions_expires_at(self, session: AsyncSession) -> None:
        result = await session.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE tablename = 'exceptions' "
                "AND indexname = 'ix_exceptions_expires_at'"
            )
        )
        assert result.scalar() is not None

    async def test_index_exceptions_finding_id(self, session: AsyncSession) -> None:
        result = await session.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE tablename = 'exceptions' "
                "AND indexname = 'ix_exceptions_finding_id'"
            )
        )
        assert result.scalar() is not None


# ---------------------------------------------------------------------------
# Integration: both tables exist
# ---------------------------------------------------------------------------

class TestMigrationIntegration:
    async def test_both_remediation_tables_exist(
        self, session: AsyncSession
    ) -> None:
        expected = {"remediation_recommendations", "exceptions"}
        result = await session.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' "
                "AND table_name = ANY(:names)"
            ),
            {"names": list(expected)},
        )
        found = {row[0] for row in result}
        assert found == expected, f"Missing tables: {expected - found}"

    async def test_exceptions_expires_at_not_nullable(
        self, session: AsyncSession
    ) -> None:
        result = await session.execute(
            text(
                "SELECT is_nullable FROM information_schema.columns "
                "WHERE table_name = 'exceptions' "
                "AND column_name = 'expires_at'"
            )
        )
        is_nullable = result.scalar()
        assert is_nullable == "NO", "exceptions.expires_at must be NOT NULL"

    async def test_exceptions_justification_not_nullable(
        self, session: AsyncSession
    ) -> None:
        result = await session.execute(
            text(
                "SELECT is_nullable FROM information_schema.columns "
                "WHERE table_name = 'exceptions' "
                "AND column_name = 'justification'"
            )
        )
        is_nullable = result.scalar()
        assert is_nullable == "NO", "exceptions.justification must be NOT NULL"
