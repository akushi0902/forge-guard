"""Unit tests for ReleaseRetriever (WO-067).

Tests cover: assessment with decision, assessment without decision (pending),
no assessment at all, and DB error handling.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from forgeguard.services.agent.knowledge_base.release_retriever import ReleaseRetriever

_USER_ID = uuid.UUID("a5000000-0000-0000-0000-000000000001")
_SVC_ID = uuid.UUID("b5000000-0000-0000-0000-000000000001")
_RELEASE_ID = uuid.UUID("c5000000-0000-0000-0000-000000000001")
_DECISION_ID = uuid.UUID("d5000000-0000-0000-0000-000000000001")
_NOW = datetime(2026, 8, 13, tzinfo=timezone.utc)


def _make_pool(row=None, raises=None):
    conn = MagicMock()
    if raises:
        conn.fetchrow = AsyncMock(side_effect=raises)
    else:
        conn.fetchrow = AsyncMock(return_value=row)

    ctx_mgr = MagicMock()
    ctx_mgr.__aenter__ = AsyncMock(return_value=conn)
    ctx_mgr.__aexit__ = AsyncMock(return_value=False)

    pool = MagicMock()
    pool.acquire = MagicMock(return_value=ctx_mgr)
    return pool


def _release_row(decision="APPROVE", has_decision=True):
    row = MagicMock()
    data = {
        "release_assessment_id": _RELEASE_ID,
        "commit_sha": "abc123",
        "pr_reference": "https://github.com/org/repo/pull/42",
        "trigger_type": "manual",
        "assessment_status": "completed",
        "assessment_created_at": _NOW,
        "assessment_completed_at": _NOW,
        "decision_id": _DECISION_ID if has_decision else None,
        "decision": decision if has_decision else None,
        "health_score_at_decision": Decimal("78.5") if has_decision else None,
        "risk_score_at_decision": Decimal("25.0") if has_decision else None,
        "decided_by_role": "tech_lead" if has_decision else None,
        "was_escalated": False,
        "rationale": "Looks good" if has_decision else None,
        "comment": None,
        "decision_created_at": _NOW if has_decision else None,
    }
    row.__getitem__ = lambda self, k: data[k]
    row.__bool__ = lambda self: True
    return row


# ---------------------------------------------------------------------------
# Happy path — assessment with decision
# ---------------------------------------------------------------------------

class TestReleaseRetrieverWithDecision:
    @pytest.mark.asyncio
    async def test_domain_is_release(self):
        pool = _make_pool(_release_row())
        retriever = ReleaseRetriever(pool)
        ctx = await retriever.retrieve(_USER_ID, _SVC_ID)

        assert ctx.domain == "release"
        assert not ctx.is_empty
        assert not ctx.is_degraded

    @pytest.mark.asyncio
    async def test_decision_value_returned(self):
        pool = _make_pool(_release_row(decision="BLOCK"))
        retriever = ReleaseRetriever(pool)
        ctx = await retriever.retrieve(_USER_ID, _SVC_ID)

        assert ctx.data["decision"]["decision"] == "BLOCK"

    @pytest.mark.asyncio
    async def test_risk_score_returned(self):
        pool = _make_pool(_release_row())
        retriever = ReleaseRetriever(pool)
        ctx = await retriever.retrieve(_USER_ID, _SVC_ID)

        assert ctx.data["decision"]["risk_score_at_decision"] == pytest.approx(25.0)

    @pytest.mark.asyncio
    async def test_health_score_returned(self):
        pool = _make_pool(_release_row())
        retriever = ReleaseRetriever(pool)
        ctx = await retriever.retrieve(_USER_ID, _SVC_ID)

        assert ctx.data["decision"]["health_score_at_decision"] == pytest.approx(78.5)

    @pytest.mark.asyncio
    async def test_escalation_status_returned(self):
        pool = _make_pool(_release_row())
        retriever = ReleaseRetriever(pool)
        ctx = await retriever.retrieve(_USER_ID, _SVC_ID)

        assert ctx.data["decision"]["was_escalated"] is False

    @pytest.mark.asyncio
    async def test_decided_by_role_returned(self):
        pool = _make_pool(_release_row())
        retriever = ReleaseRetriever(pool)
        ctx = await retriever.retrieve(_USER_ID, _SVC_ID)

        assert ctx.data["decision"]["decided_by_role"] == "tech_lead"

    @pytest.mark.asyncio
    async def test_commit_sha_returned(self):
        pool = _make_pool(_release_row())
        retriever = ReleaseRetriever(pool)
        ctx = await retriever.retrieve(_USER_ID, _SVC_ID)

        assert ctx.data["commit_sha"] == "abc123"

    @pytest.mark.asyncio
    async def test_assessment_created_at_is_iso_string(self):
        pool = _make_pool(_release_row())
        retriever = ReleaseRetriever(pool)
        ctx = await retriever.retrieve(_USER_ID, _SVC_ID)

        assert ctx.data["assessment_created_at"] == _NOW.isoformat()


# ---------------------------------------------------------------------------
# Pending decision (assessment exists, no decision yet)
# ---------------------------------------------------------------------------

class TestReleaseRetrieverPending:
    @pytest.mark.asyncio
    async def test_pending_decision_returned(self):
        pool = _make_pool(_release_row(has_decision=False))
        retriever = ReleaseRetriever(pool)
        ctx = await retriever.retrieve(_USER_ID, _SVC_ID)

        assert ctx.data["decision"]["decision"] == "pending"

    @pytest.mark.asyncio
    async def test_pending_message_is_informative(self):
        pool = _make_pool(_release_row(has_decision=False))
        retriever = ReleaseRetriever(pool)
        ctx = await retriever.retrieve(_USER_ID, _SVC_ID)

        assert "pending" in ctx.data["decision"]["message"].lower()

    @pytest.mark.asyncio
    async def test_pending_is_not_empty(self):
        # The assessment exists even if no decision is made yet.
        pool = _make_pool(_release_row(has_decision=False))
        retriever = ReleaseRetriever(pool)
        ctx = await retriever.retrieve(_USER_ID, _SVC_ID)

        assert not ctx.is_empty


# ---------------------------------------------------------------------------
# Empty path (no release assessment)
# ---------------------------------------------------------------------------

class TestReleaseRetrieverEmpty:
    @pytest.mark.asyncio
    async def test_empty_when_no_assessment(self):
        pool = _make_pool(row=None)
        retriever = ReleaseRetriever(pool)
        ctx = await retriever.retrieve(_USER_ID, _SVC_ID)

        assert ctx.is_empty is True
        assert ctx.domain == "release"

    @pytest.mark.asyncio
    async def test_empty_reason_is_informative(self):
        pool = _make_pool(row=None)
        retriever = ReleaseRetriever(pool)
        ctx = await retriever.retrieve(_USER_ID, _SVC_ID)

        assert "release" in ctx.empty_reason.lower()

    @pytest.mark.asyncio
    async def test_all_decisions_covered(self):
        for decision in ("APPROVE", "CONDITIONAL_APPROVE", "BLOCK"):
            pool = _make_pool(_release_row(decision=decision))
            retriever = ReleaseRetriever(pool)
            ctx = await retriever.retrieve(_USER_ID, _SVC_ID)
            assert ctx.data["decision"]["decision"] == decision


# ---------------------------------------------------------------------------
# Error path
# ---------------------------------------------------------------------------

class TestReleaseRetrieverError:
    @pytest.mark.asyncio
    async def test_db_error_returns_degraded(self):
        pool = _make_pool(raises=Exception("DB offline"))
        retriever = ReleaseRetriever(pool)
        ctx = await retriever.retrieve(_USER_ID, _SVC_ID)

        assert ctx.is_degraded is True
        assert "DB offline" in ctx.degraded_reason

    @pytest.mark.asyncio
    async def test_degraded_does_not_raise(self):
        pool = _make_pool(raises=RuntimeError("pool exhausted"))
        retriever = ReleaseRetriever(pool)
        ctx = await retriever.retrieve(_USER_ID, _SVC_ID)
        assert ctx is not None

    @pytest.mark.asyncio
    async def test_retrieval_time_recorded(self):
        pool = _make_pool(_release_row())
        retriever = ReleaseRetriever(pool)
        ctx = await retriever.retrieve(_USER_ID, _SVC_ID)

        assert ctx.retrieval_time_ms >= 0
