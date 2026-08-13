"""Unit tests for ContextAssembler (WO-067).

Tests cover: intent-to-retriever mapping, concurrent execution, partial
failure handling, timeout behaviour, and service access scoping.
"""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from forgeguard.services.agent.intent_classifier import IntentCategory
from forgeguard.services.agent.knowledge_base.base_retriever import RetrievalContext
from forgeguard.services.agent.knowledge_base.context_assembler import (
    ContextAssembler,
    ContextBundle,
)

_USER_ID = uuid.UUID("a3000000-0000-0000-0000-000000000001")
_SVC_ID = uuid.UUID("b3000000-0000-0000-0000-000000000001")


def _ok_ctx(domain="health") -> RetrievalContext:
    return RetrievalContext(domain=domain, data={"service_id": str(_SVC_ID)})


def _empty_ctx(domain="health") -> RetrievalContext:
    return RetrievalContext(domain=domain, is_empty=True, empty_reason="no data")


def _degraded_ctx(domain="health") -> RetrievalContext:
    return RetrievalContext(domain=domain, is_degraded=True, degraded_reason="error")


def _make_assembler(
    *,
    health_ctx=None,
    findings_ctx=None,
    policy_ctx=None,
    release_ctx=None,
    authorized=True,
):
    """Build a ContextAssembler with mocked sub-components."""
    pool = MagicMock()
    assembler = ContextAssembler(pool)

    # Mock individual retrievers
    assembler._health.retrieve = AsyncMock(return_value=health_ctx or _ok_ctx("health"))
    assembler._findings.retrieve = AsyncMock(return_value=findings_ctx or _ok_ctx("findings"))
    assembler._policy.retrieve = AsyncMock(return_value=policy_ctx or _ok_ctx("policy"))
    assembler._release.retrieve = AsyncMock(return_value=release_ctx or _ok_ctx("release"))

    # Mock access resolver
    assembler._access.is_authorized = AsyncMock(return_value=authorized)

    return assembler


# ---------------------------------------------------------------------------
# Intent-to-retriever mapping
# ---------------------------------------------------------------------------

class TestIntentRetrieverMapping:
    @pytest.mark.asyncio
    async def test_health_score_uses_health_retriever(self):
        asm = _make_assembler()
        bundle = await asm.assemble(
            user_id=_USER_ID,
            actor_role="developer",
            intent=IntentCategory.HEALTH_SCORE,
            service_id=_SVC_ID,
        )
        asm._health.retrieve.assert_awaited_once()
        asm._findings.retrieve.assert_not_awaited()
        assert bundle.health is not None

    @pytest.mark.asyncio
    async def test_findings_uses_findings_and_policy(self):
        asm = _make_assembler()
        bundle = await asm.assemble(
            user_id=_USER_ID,
            actor_role="developer",
            intent=IntentCategory.FINDINGS,
            service_id=_SVC_ID,
        )
        asm._findings.retrieve.assert_awaited_once()
        asm._policy.retrieve.assert_awaited_once()
        assert bundle.findings is not None
        assert bundle.policy is not None

    @pytest.mark.asyncio
    async def test_remediation_uses_findings_and_policy(self):
        asm = _make_assembler()
        await asm.assemble(
            user_id=_USER_ID,
            actor_role="developer",
            intent=IntentCategory.REMEDIATION,
            service_id=_SVC_ID,
        )
        asm._findings.retrieve.assert_awaited_once()
        asm._policy.retrieve.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_release_status_uses_release_and_health(self):
        asm = _make_assembler()
        bundle = await asm.assemble(
            user_id=_USER_ID,
            actor_role="developer",
            intent=IntentCategory.RELEASE_STATUS,
            service_id=_SVC_ID,
        )
        asm._release.retrieve.assert_awaited_once()
        asm._health.retrieve.assert_awaited_once()
        assert bundle.release is not None
        assert bundle.health is not None

    @pytest.mark.asyncio
    async def test_policy_rules_uses_only_policy(self):
        asm = _make_assembler()
        await asm.assemble(
            user_id=_USER_ID,
            actor_role="developer",
            intent=IntentCategory.POLICY_RULES,
            service_id=_SVC_ID,
        )
        asm._policy.retrieve.assert_awaited_once()
        asm._health.retrieve.assert_not_awaited()
        asm._findings.retrieve.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_general_help_no_retrievers_called(self):
        asm = _make_assembler()
        bundle = await asm.assemble(
            user_id=_USER_ID,
            actor_role="developer",
            intent=IntentCategory.GENERAL_HELP,
            service_id=_SVC_ID,
        )
        asm._health.retrieve.assert_not_awaited()
        asm._findings.retrieve.assert_not_awaited()
        assert bundle.health is None


# ---------------------------------------------------------------------------
# Service access scoping
# ---------------------------------------------------------------------------

class TestServiceAccessScoping:
    @pytest.mark.asyncio
    async def test_unauthorized_returns_unauthorized_bundle(self):
        asm = _make_assembler(authorized=False)
        bundle = await asm.assemble(
            user_id=_USER_ID,
            actor_role="developer",
            intent=IntentCategory.HEALTH_SCORE,
            service_id=_SVC_ID,
        )
        assert bundle.is_unauthorized is True
        assert len(bundle.unauthorized_message) > 0
        asm._health.retrieve.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_service_id_skips_retrieval(self):
        asm = _make_assembler()
        bundle = await asm.assemble(
            user_id=_USER_ID,
            actor_role="developer",
            intent=IntentCategory.HEALTH_SCORE,
            service_id=None,
        )
        asm._health.retrieve.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_authorized_calls_retrievers(self):
        asm = _make_assembler(authorized=True)
        bundle = await asm.assemble(
            user_id=_USER_ID,
            actor_role="developer",
            intent=IntentCategory.HEALTH_SCORE,
            service_id=_SVC_ID,
        )
        assert bundle.is_unauthorized is False


# ---------------------------------------------------------------------------
# Partial failure handling
# ---------------------------------------------------------------------------

class TestPartialFailureHandling:
    @pytest.mark.asyncio
    async def test_degraded_retriever_marks_bundle_degraded(self):
        asm = _make_assembler(findings_ctx=_degraded_ctx("findings"))
        bundle = await asm.assemble(
            user_id=_USER_ID,
            actor_role="developer",
            intent=IntentCategory.FINDINGS,
            service_id=_SVC_ID,
        )
        assert bundle.is_degraded is True

    @pytest.mark.asyncio
    async def test_one_degraded_does_not_null_other_domains(self):
        asm = _make_assembler(
            findings_ctx=_degraded_ctx("findings"),
            policy_ctx=_ok_ctx("policy"),
        )
        bundle = await asm.assemble(
            user_id=_USER_ID,
            actor_role="developer",
            intent=IntentCategory.FINDINGS,
            service_id=_SVC_ID,
        )
        # Policy succeeded; findings degraded but both are present.
        assert bundle.policy is not None
        assert bundle.findings is not None

    @pytest.mark.asyncio
    async def test_retriever_exception_returns_degraded_context(self):
        asm = _make_assembler()
        asm._health.retrieve = AsyncMock(side_effect=RuntimeError("DB down"))

        bundle = await asm.assemble(
            user_id=_USER_ID,
            actor_role="developer",
            intent=IntentCategory.HEALTH_SCORE,
            service_id=_SVC_ID,
        )
        assert bundle.is_degraded is True

    @pytest.mark.asyncio
    async def test_timeout_returns_degraded_context(self):
        async def _slow(*_a, **_kw):
            await asyncio.sleep(10)
            return _ok_ctx("health")

        asm = _make_assembler()
        asm._health.retrieve = _slow

        bundle = await asm.assemble(
            user_id=_USER_ID,
            actor_role="developer",
            intent=IntentCategory.HEALTH_SCORE,
            service_id=_SVC_ID,
        )
        assert bundle.is_degraded is True


# ---------------------------------------------------------------------------
# ContextBundle.to_prompt_dict
# ---------------------------------------------------------------------------

class TestContextBundleToPromptDict:
    def test_prompt_dict_has_intent(self):
        bundle = ContextBundle(intent="health_score")
        d = bundle.to_prompt_dict()
        assert d["intent"] == "health_score"

    def test_prompt_dict_unauthorized_returns_message(self):
        bundle = ContextBundle(
            intent="health_score",
            is_unauthorized=True,
            unauthorized_message="Access denied",
        )
        d = bundle.to_prompt_dict()
        assert d["unauthorized_message"] == "Access denied"
        assert "health_context" not in d

    def test_prompt_dict_includes_health_when_present(self):
        bundle = ContextBundle(
            intent="health_score",
            health=RetrievalContext(domain="health", data={"overall_score": 85.0}),
        )
        d = bundle.to_prompt_dict()
        assert "health_context" in d
        assert d["health_context"]["overall_score"] == 85.0

    def test_prompt_dict_empty_context_shows_unavailable(self):
        bundle = ContextBundle(
            intent="health_score",
            health=RetrievalContext(
                domain="health", is_empty=True, empty_reason="no data"
            ),
        )
        d = bundle.to_prompt_dict()
        assert d["health_context"]["status"] == "unavailable"
        assert "no data" in d["health_context"]["reason"]
