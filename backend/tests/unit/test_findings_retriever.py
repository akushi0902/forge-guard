"""Unit tests for FindingsRetriever (WO-067).

Tests cover: normal retrieval, severity/dimension filtering, empty results,
text search, missing remediation, and DB error handling.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from forgeguard.services.agent.knowledge_base.findings_retriever import FindingsRetriever

_USER_ID = uuid.UUID("a2000000-0000-0000-0000-000000000001")
_SVC_ID = uuid.UUID("b2000000-0000-0000-0000-000000000001")
_FINDING_ID = uuid.UUID("f2000000-0000-0000-0000-000000000001")
_REC_ID = uuid.UUID("r2000000-0000-0000-0000-000000000001")
_RULE_ID = uuid.UUID("p2000000-0000-0000-0000-000000000001")
_NOW = datetime(2026, 8, 13, tzinfo=timezone.utc)


def _make_pool(rows=None, raises=None):
    conn = MagicMock()
    if raises:
        conn.fetch = AsyncMock(side_effect=raises)
    else:
        conn.fetch = AsyncMock(return_value=rows or [])

    ctx_mgr = MagicMock()
    ctx_mgr.__aenter__ = AsyncMock(return_value=conn)
    ctx_mgr.__aexit__ = AsyncMock(return_value=False)

    pool = MagicMock()
    pool.acquire = MagicMock(return_value=ctx_mgr)
    return pool


def _finding_row(
    severity="critical",
    dimension="security",
    status="open",
    title="Test finding",
    has_remediation=True,
):
    row = MagicMock()
    data = {
        "finding_id": _FINDING_ID,
        "assessment_id": uuid.uuid4(),
        "service_id": _SVC_ID,
        "policy_rule_id": _RULE_ID,
        "severity": severity,
        "dimension": dimension,
        "status": status,
        "title": title,
        "description": "A test description",
        "finding_confidence": Decimal("0.85"),
        "finding_created_at": _NOW,
        "resolved_at": None,
        "recommendation_id": _REC_ID if has_remediation else None,
        "recommendation_text": "Fix this now" if has_remediation else None,
        "implementation_guide": "Step 1…" if has_remediation else None,
        "business_impact": "High risk" if has_remediation else None,
        "recommendation_confidence": Decimal("0.90") if has_remediation else None,
        "recommendation_source": "ai_generated" if has_remediation else None,
    }
    row.__getitem__ = lambda self, k: data[k]
    return row


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

class TestFindingsRetrieverHappyPath:
    @pytest.mark.asyncio
    async def test_domain_is_findings(self):
        pool = _make_pool([_finding_row()])
        retriever = FindingsRetriever(pool)
        ctx = await retriever.retrieve(_USER_ID, _SVC_ID)

        assert ctx.domain == "findings"
        assert not ctx.is_empty
        assert not ctx.is_degraded

    @pytest.mark.asyncio
    async def test_returns_finding_list(self):
        pool = _make_pool([_finding_row(), _finding_row(severity="high")])
        retriever = FindingsRetriever(pool)
        ctx = await retriever.retrieve(_USER_ID, _SVC_ID)

        assert ctx.data["total_returned"] == 2
        assert len(ctx.data["findings"]) == 2

    @pytest.mark.asyncio
    async def test_finding_has_required_fields(self):
        pool = _make_pool([_finding_row()])
        retriever = FindingsRetriever(pool)
        ctx = await retriever.retrieve(_USER_ID, _SVC_ID)

        finding = ctx.data["findings"][0]
        assert "finding_id" in finding
        assert "severity" in finding
        assert "dimension" in finding
        assert "title" in finding
        assert "remediation" in finding

    @pytest.mark.asyncio
    async def test_remediation_text_included(self):
        pool = _make_pool([_finding_row(has_remediation=True)])
        retriever = FindingsRetriever(pool)
        ctx = await retriever.retrieve(_USER_ID, _SVC_ID)

        rem = ctx.data["findings"][0]["remediation"]
        assert rem is not None
        assert rem["recommendation_text"] == "Fix this now"
        assert rem["source"] == "ai_generated"


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------

class TestFindingsRetrieverFiltering:
    @pytest.mark.asyncio
    async def test_severity_filter_passed_to_query(self):
        pool = _make_pool([_finding_row(severity="critical")])
        retriever = FindingsRetriever(pool)
        ctx = await retriever.retrieve(
            _USER_ID, _SVC_ID, query_params={"severity": "critical"}
        )

        assert ctx.data["filters_applied"]["severity"] == "critical"

    @pytest.mark.asyncio
    async def test_dimension_filter_passed_to_query(self):
        pool = _make_pool([_finding_row(dimension="security")])
        retriever = FindingsRetriever(pool)
        ctx = await retriever.retrieve(
            _USER_ID, _SVC_ID, query_params={"dimension": "security"}
        )

        assert ctx.data["filters_applied"]["dimension"] == "security"

    @pytest.mark.asyncio
    async def test_search_text_filter(self):
        pool = _make_pool([_finding_row(title="Missing README")])
        retriever = FindingsRetriever(pool)
        ctx = await retriever.retrieve(
            _USER_ID, _SVC_ID, query_params={"search_text": "README"}
        )

        assert ctx.data["filters_applied"]["search_text"] == "README"


# ---------------------------------------------------------------------------
# Missing remediation
# ---------------------------------------------------------------------------

class TestFindingsMissingRemediation:
    @pytest.mark.asyncio
    async def test_missing_remediation_returns_pending_message(self):
        pool = _make_pool([_finding_row(has_remediation=False)])
        retriever = FindingsRetriever(pool)
        ctx = await retriever.retrieve(_USER_ID, _SVC_ID)

        rem = ctx.data["findings"][0]["remediation"]
        assert rem["source"] == "pending"
        assert "pending" in rem["recommendation_text"].lower()


# ---------------------------------------------------------------------------
# Empty path
# ---------------------------------------------------------------------------

class TestFindingsRetrieverEmpty:
    @pytest.mark.asyncio
    async def test_empty_when_no_findings(self):
        pool = _make_pool([])
        retriever = FindingsRetriever(pool)
        ctx = await retriever.retrieve(_USER_ID, _SVC_ID)

        assert ctx.is_empty is True
        assert ctx.domain == "findings"
        assert len(ctx.empty_reason) > 0

    @pytest.mark.asyncio
    async def test_empty_reason_mentions_severity_filter(self):
        pool = _make_pool([])
        retriever = FindingsRetriever(pool)
        ctx = await retriever.retrieve(
            _USER_ID, _SVC_ID, query_params={"severity": "critical"}
        )

        assert "critical" in ctx.empty_reason


# ---------------------------------------------------------------------------
# Error path
# ---------------------------------------------------------------------------

class TestFindingsRetrieverError:
    @pytest.mark.asyncio
    async def test_db_error_returns_degraded(self):
        pool = _make_pool(raises=Exception("query failed"))
        retriever = FindingsRetriever(pool)
        ctx = await retriever.retrieve(_USER_ID, _SVC_ID)

        assert ctx.is_degraded is True
        assert "query failed" in ctx.degraded_reason

    @pytest.mark.asyncio
    async def test_degraded_does_not_raise(self):
        pool = _make_pool(raises=RuntimeError("timeout"))
        retriever = FindingsRetriever(pool)
        ctx = await retriever.retrieve(_USER_ID, _SVC_ID)

        assert ctx is not None
