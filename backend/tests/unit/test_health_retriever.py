"""Unit tests for HealthRetriever (WO-067).

Tests cover: normal retrieval, empty (no assessments), degraded (DB error).
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from forgeguard.services.agent.knowledge_base.health_retriever import HealthRetriever

_USER_ID = uuid.UUID("a1000000-0000-0000-0000-000000000001")
_SVC_ID = uuid.UUID("b1000000-0000-0000-0000-000000000001")
_ASSESS_ID = uuid.UUID("c1000000-0000-0000-0000-000000000001")
_NOW = datetime(2026, 8, 13, tzinfo=timezone.utc)


def _make_pool(health_row=None, severity_rows=None, raises=None):
    """Build a mock asyncpg pool for HealthRetriever tests."""
    conn = MagicMock()
    if raises:
        conn.fetchrow = AsyncMock(side_effect=raises)
    else:
        conn.fetchrow = AsyncMock(return_value=health_row)
        conn.fetch = AsyncMock(return_value=severity_rows or [])

    ctx_mgr = MagicMock()
    ctx_mgr.__aenter__ = AsyncMock(return_value=conn)
    ctx_mgr.__aexit__ = AsyncMock(return_value=False)

    pool = MagicMock()
    pool.acquire = MagicMock(return_value=ctx_mgr)
    return pool


def _health_row(overall_score=85.0, dimensions=None):
    row = MagicMock()
    row.__getitem__ = lambda self, k: {
        "service_id": _SVC_ID,
        "service_name": "test-service",
        "assessment_id": _ASSESS_ID,
        "evaluated_at": _NOW,
        "assessment_status": "completed",
        "overall_score": Decimal(str(overall_score)),
        "dimension_scores": dimensions or {
            "code_quality": 80.0,
            "test_coverage": 85.0,
            "security": 90.0,
            "documentation": 75.0,
            "operations_readiness": 88.0,
        },
        "weights_used": {},
    }[k]
    row.__bool__ = lambda self: True
    return row


def _severity_row(severity, count):
    row = MagicMock()
    row.__getitem__ = lambda self, k: {"severity": severity, "cnt": count}[k]
    return row


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

class TestHealthRetrieverHappyPath:
    @pytest.mark.asyncio
    async def test_returns_health_domain(self):
        pool = _make_pool(
            health_row=_health_row(),
            severity_rows=[_severity_row("critical", 2), _severity_row("high", 5)],
        )
        retriever = HealthRetriever(pool)
        ctx = await retriever.retrieve(_USER_ID, _SVC_ID)

        assert ctx.domain == "health"
        assert not ctx.is_empty
        assert not ctx.is_degraded

    @pytest.mark.asyncio
    async def test_overall_score_present(self):
        pool = _make_pool(
            health_row=_health_row(overall_score=72.5),
            severity_rows=[],
        )
        retriever = HealthRetriever(pool)
        ctx = await retriever.retrieve(_USER_ID, _SVC_ID)

        assert ctx.data["overall_score"] == pytest.approx(72.5)

    @pytest.mark.asyncio
    async def test_finding_counts_populated(self):
        pool = _make_pool(
            health_row=_health_row(),
            severity_rows=[
                _severity_row("critical", 3),
                _severity_row("high", 7),
                _severity_row("medium", 12),
            ],
        )
        retriever = HealthRetriever(pool)
        ctx = await retriever.retrieve(_USER_ID, _SVC_ID)

        counts = ctx.data["finding_counts_by_severity"]
        assert counts["critical"] == 3
        assert counts["high"] == 7
        assert counts["medium"] == 12
        assert counts["low"] == 0  # not in severity_rows → defaults to 0

    @pytest.mark.asyncio
    async def test_dimension_scores_returned(self):
        dims = {"code_quality": 80.0, "test_coverage": 65.0}
        pool = _make_pool(health_row=_health_row(dimensions=dims), severity_rows=[])
        retriever = HealthRetriever(pool)
        ctx = await retriever.retrieve(_USER_ID, _SVC_ID)

        assert ctx.data["dimension_scores"] == dims

    @pytest.mark.asyncio
    async def test_evaluated_at_is_iso_string(self):
        pool = _make_pool(health_row=_health_row(), severity_rows=[])
        retriever = HealthRetriever(pool)
        ctx = await retriever.retrieve(_USER_ID, _SVC_ID)

        assert ctx.data["evaluated_at"] == _NOW.isoformat()

    @pytest.mark.asyncio
    async def test_service_name_included(self):
        pool = _make_pool(health_row=_health_row(), severity_rows=[])
        retriever = HealthRetriever(pool)
        ctx = await retriever.retrieve(_USER_ID, _SVC_ID)

        assert ctx.data["service_name"] == "test-service"


# ---------------------------------------------------------------------------
# Empty path (no assessments)
# ---------------------------------------------------------------------------

class TestHealthRetrieverEmpty:
    @pytest.mark.asyncio
    async def test_empty_context_when_no_assessment(self):
        pool = _make_pool(health_row=None)
        retriever = HealthRetriever(pool)
        ctx = await retriever.retrieve(_USER_ID, _SVC_ID)

        assert ctx.is_empty is True
        assert ctx.domain == "health"
        assert len(ctx.empty_reason) > 0

    @pytest.mark.asyncio
    async def test_empty_reason_is_informative(self):
        pool = _make_pool(health_row=None)
        retriever = HealthRetriever(pool)
        ctx = await retriever.retrieve(_USER_ID, _SVC_ID)

        assert "assessment" in ctx.empty_reason.lower()


# ---------------------------------------------------------------------------
# Degraded path (DB error)
# ---------------------------------------------------------------------------

class TestHealthRetrieverDegraded:
    @pytest.mark.asyncio
    async def test_db_error_returns_degraded(self):
        pool = _make_pool(raises=Exception("connection refused"))
        retriever = HealthRetriever(pool)
        ctx = await retriever.retrieve(_USER_ID, _SVC_ID)

        assert ctx.is_degraded is True
        assert ctx.domain == "health"
        assert "connection refused" in ctx.degraded_reason

    @pytest.mark.asyncio
    async def test_degraded_does_not_raise(self):
        pool = _make_pool(raises=RuntimeError("DB timeout"))
        retriever = HealthRetriever(pool)
        # Should not raise — returns degraded context.
        ctx = await retriever.retrieve(_USER_ID, _SVC_ID)
        assert ctx is not None

    @pytest.mark.asyncio
    async def test_retrieval_time_populated(self):
        pool = _make_pool(health_row=_health_row(), severity_rows=[])
        retriever = HealthRetriever(pool)
        ctx = await retriever.retrieve(_USER_ID, _SVC_ID)

        assert ctx.retrieval_time_ms >= 0
