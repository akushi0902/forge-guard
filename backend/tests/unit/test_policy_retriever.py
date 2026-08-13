"""Unit tests for PolicyRetriever (WO-067).

Tests cover: normal retrieval, dimension filtering, rule_id filtering,
empty results, and DB error handling.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from forgeguard.services.agent.knowledge_base.policy_retriever import PolicyRetriever

_USER_ID = uuid.UUID("a4000000-0000-0000-0000-000000000001")
_SVC_ID = uuid.UUID("b4000000-0000-0000-0000-000000000001")
_RULE_ID = uuid.UUID("c4000000-0000-0000-0000-000000000001")
_POLICY_ID = uuid.UUID("d4000000-0000-0000-0000-000000000001")
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


def _rule_row(
    dimension="security",
    severity="high",
    name="Test Rule",
    weight=1.0,
):
    row = MagicMock()
    data = {
        "rule_id": _RULE_ID,
        "rule_name": name,
        "rule_type": "threshold_gte",
        "threshold_config": {"operator": "gte", "value": 80, "unit": "percent"},
        "severity": severity,
        "weight": Decimal(str(weight)),
        "rule_is_active": True,
        "policy_id": _POLICY_ID,
        "policy_name": f"{dimension} Policy",
        "dimension": dimension,
        "policy_description": f"Policy for {dimension}",
        "policy_version": 1,
        "policy_is_active": True,
    }
    row.__getitem__ = lambda self, k: data[k]
    return row


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

class TestPolicyRetrieverHappyPath:
    @pytest.mark.asyncio
    async def test_domain_is_policy(self):
        pool = _make_pool([_rule_row()])
        retriever = PolicyRetriever(pool)
        ctx = await retriever.retrieve(_USER_ID, _SVC_ID)

        assert ctx.domain == "policy"
        assert not ctx.is_empty
        assert not ctx.is_degraded

    @pytest.mark.asyncio
    async def test_returns_rules_list(self):
        pool = _make_pool([_rule_row("security"), _rule_row("code_quality")])
        retriever = PolicyRetriever(pool)
        ctx = await retriever.retrieve(_USER_ID, _SVC_ID)

        assert ctx.data["total_rules"] == 2
        assert len(ctx.data["rules"]) == 2

    @pytest.mark.asyncio
    async def test_rule_has_required_fields(self):
        pool = _make_pool([_rule_row()])
        retriever = PolicyRetriever(pool)
        ctx = await retriever.retrieve(_USER_ID, _SVC_ID)

        rule = ctx.data["rules"][0]
        for key in ("rule_id", "rule_name", "severity", "weight", "dimension", "threshold_config"):
            assert key in rule, f"Missing key: {key}"

    @pytest.mark.asyncio
    async def test_rules_grouped_by_dimension(self):
        pool = _make_pool([
            _rule_row("security"),
            _rule_row("security"),
            _rule_row("code_quality"),
        ])
        retriever = PolicyRetriever(pool)
        ctx = await retriever.retrieve(_USER_ID, _SVC_ID)

        by_dim = ctx.data["rules_by_dimension"]
        assert "security" in by_dim
        assert len(by_dim["security"]) == 2
        assert "code_quality" in by_dim

    @pytest.mark.asyncio
    async def test_weight_is_float(self):
        pool = _make_pool([_rule_row(weight=1.5)])
        retriever = PolicyRetriever(pool)
        ctx = await retriever.retrieve(_USER_ID, _SVC_ID)

        rule = ctx.data["rules"][0]
        assert isinstance(rule["weight"], float)
        assert rule["weight"] == pytest.approx(1.5)


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------

class TestPolicyRetrieverFiltering:
    @pytest.mark.asyncio
    async def test_dimension_filter_recorded(self):
        pool = _make_pool([_rule_row("security")])
        retriever = PolicyRetriever(pool)
        ctx = await retriever.retrieve(
            _USER_ID, _SVC_ID, query_params={"dimension": "security"}
        )

        assert ctx.data["filters_applied"]["dimension"] == "security"

    @pytest.mark.asyncio
    async def test_rule_id_filter_recorded(self):
        pool = _make_pool([_rule_row()])
        retriever = PolicyRetriever(pool)
        ctx = await retriever.retrieve(
            _USER_ID, _SVC_ID, query_params={"rule_id": str(_RULE_ID)}
        )

        assert ctx.data["filters_applied"]["rule_id"] == str(_RULE_ID)

    @pytest.mark.asyncio
    async def test_invalid_rule_id_handled_gracefully(self):
        pool = _make_pool([_rule_row()])
        retriever = PolicyRetriever(pool)
        # Should not raise — invalid UUID falls back to no filter
        ctx = await retriever.retrieve(
            _USER_ID, _SVC_ID, query_params={"rule_id": "not-a-uuid"}
        )
        assert ctx is not None


# ---------------------------------------------------------------------------
# Empty path
# ---------------------------------------------------------------------------

class TestPolicyRetrieverEmpty:
    @pytest.mark.asyncio
    async def test_empty_when_no_rules(self):
        pool = _make_pool([])
        retriever = PolicyRetriever(pool)
        ctx = await retriever.retrieve(_USER_ID, _SVC_ID)

        assert ctx.is_empty is True
        assert ctx.domain == "policy"
        assert len(ctx.empty_reason) > 0

    @pytest.mark.asyncio
    async def test_empty_reason_mentions_dimension_filter(self):
        pool = _make_pool([])
        retriever = PolicyRetriever(pool)
        ctx = await retriever.retrieve(
            _USER_ID, _SVC_ID, query_params={"dimension": "security"}
        )

        assert "security" in ctx.empty_reason


# ---------------------------------------------------------------------------
# Error path
# ---------------------------------------------------------------------------

class TestPolicyRetrieverError:
    @pytest.mark.asyncio
    async def test_db_error_returns_degraded(self):
        pool = _make_pool(raises=Exception("connection lost"))
        retriever = PolicyRetriever(pool)
        ctx = await retriever.retrieve(_USER_ID, _SVC_ID)

        assert ctx.is_degraded is True
        assert "connection lost" in ctx.degraded_reason

    @pytest.mark.asyncio
    async def test_degraded_does_not_raise(self):
        pool = _make_pool(raises=RuntimeError("timeout"))
        retriever = PolicyRetriever(pool)
        ctx = await retriever.retrieve(_USER_ID, _SVC_ID)
        assert ctx is not None

    @pytest.mark.asyncio
    async def test_retrieval_time_recorded(self):
        pool = _make_pool([_rule_row()])
        retriever = PolicyRetriever(pool)
        ctx = await retriever.retrieve(_USER_ID, _SVC_ID)

        assert ctx.retrieval_time_ms >= 0
