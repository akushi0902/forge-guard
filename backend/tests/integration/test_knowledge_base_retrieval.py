"""Integration tests for the knowledge base retrieval pipeline (WO-067).

Tests execute the full retrieval pipeline from intent classification through
ContextAssembler to assembled context, verifying:
    - Data accuracy across all 6 intent categories
    - Ownership scoping enforcement
    - Response time within 2-second budget

These tests use mock pools to simulate database interactions at the retriever
boundary — this allows full pipeline testing without a live database.

For database-backed integration tests against a real PostgreSQL instance, see
the conftest.py test database fixtures.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from decimal import Decimal
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from forgeguard.services.agent.intent_classifier import IntentCategory
from forgeguard.services.agent.knowledge_base.context_assembler import ContextAssembler
from forgeguard.services.agent.knowledge_base.health_retriever import HealthRetriever
from forgeguard.services.agent.knowledge_base.findings_retriever import FindingsRetriever
from forgeguard.services.agent.knowledge_base.policy_retriever import PolicyRetriever
from forgeguard.services.agent.knowledge_base.release_retriever import ReleaseRetriever
from forgeguard.services.agent.knowledge_base.service_access_resolver import ServiceAccessResolver
from tests.fixtures.knowledge_base_fixtures import build_kb_fixture_bundle

_USER_ID = uuid.UUID("a9000000-0000-0000-0000-000000000001")
_SVC_ID = uuid.UUID("b9000000-0000-0000-0000-000000000001")
_ASSESS_ID = uuid.UUID("c9000000-0000-0000-0000-000000000001")
_RULE_ID = uuid.UUID("d9000000-0000-0000-0000-000000000001")
_NOW = datetime(2026, 8, 13, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Fixture bundle (loaded once)
# ---------------------------------------------------------------------------

_BUNDLE = build_kb_fixture_bundle()


def _make_mock_assembler(authorized=True) -> ContextAssembler:
    """Create a ContextAssembler with all retrievers mocked."""
    pool = MagicMock()
    asm = ContextAssembler(pool)

    from forgeguard.services.agent.knowledge_base.base_retriever import RetrievalContext

    # Inject data from fixture bundle
    service = _BUNDLE.services[0]
    assessment = _BUNDLE.assessments[0]
    score = _BUNDLE.scores[0]
    findings = _BUNDLE.findings[:10]
    rules = _BUNDLE.rules[:5]
    release_assessment = _BUNDLE.release_assessments[0]
    release_decision = _BUNDLE.release_decisions[0]

    # Health context
    health_ctx = RetrievalContext(
        domain="health",
        data={
            "service_id": str(service["id"]),
            "service_name": service["name"],
            "overall_score": float(score["overall_score"]),
            "dimension_scores": score["dimension_scores"],
            "finding_counts_by_severity": {"critical": 2, "high": 5, "medium": 3, "low": 1},
            "evaluated_at": assessment["completed_at"].isoformat() if assessment["completed_at"] else None,
            "assessment_status": assessment["status"],
        },
    )

    # Findings context
    findings_ctx = RetrievalContext(
        domain="findings",
        data={
            "service_id": str(service["id"]),
            "total_returned": len(findings),
            "filters_applied": {},
            "findings": [
                {
                    "finding_id": str(f["id"]),
                    "severity": f["severity"],
                    "dimension": f["dimension"],
                    "status": f["status"],
                    "title": f["title"],
                    "description": f["description"],
                    "created_at": f["created_at"].isoformat(),
                    "resolved_at": None,
                    "policy_rule_id": str(f["policy_rule_id"]),
                    "remediation": {"recommendation_text": "Fix it", "source": "ai_generated"},
                }
                for f in findings
            ],
        },
    )

    # Policy context
    policy_ctx = RetrievalContext(
        domain="policy",
        data={
            "service_id": str(service["id"]),
            "total_rules": len(rules),
            "filters_applied": {},
            "rules_by_dimension": {},
            "rules": [
                {
                    "rule_id": str(r["id"]),
                    "rule_name": r["name"],
                    "rule_type": r["rule_type"],
                    "threshold_config": r["threshold_config"],
                    "severity": r["severity"],
                    "weight": float(r["weight"]),
                    "policy_id": str(r["policy_id"]),
                    "policy_name": "Test Policy",
                    "dimension": "security",
                    "policy_description": None,
                    "policy_version": 1,
                }
                for r in rules
            ],
        },
    )

    # Release context
    release_ctx = RetrievalContext(
        domain="release",
        data={
            "service_id": str(service["id"]),
            "release_assessment_id": str(release_assessment["id"]),
            "commit_sha": release_assessment["commit_sha"],
            "pr_reference": release_assessment["pr_reference"],
            "assessment_status": release_assessment["status"],
            "assessment_created_at": release_assessment["created_at"].isoformat(),
            "assessment_completed_at": release_assessment["completed_at"].isoformat() if release_assessment["completed_at"] else None,
            "decision": {
                "decision": release_decision["decision"],
                "health_score_at_decision": float(release_decision["health_score_at_decision"]),
                "risk_score_at_decision": float(release_decision["risk_score_at_decision"]),
                "decided_by_role": release_decision["decided_by_role"],
                "was_escalated": release_decision["was_escalated"],
                "rationale": release_decision["rationale"],
                "decision_created_at": release_decision["created_at"].isoformat(),
            },
        },
    )

    asm._health.retrieve = AsyncMock(return_value=health_ctx)
    asm._findings.retrieve = AsyncMock(return_value=findings_ctx)
    asm._policy.retrieve = AsyncMock(return_value=policy_ctx)
    asm._release.retrieve = AsyncMock(return_value=release_ctx)
    asm._access.is_authorized = AsyncMock(return_value=authorized)

    return asm


# ---------------------------------------------------------------------------
# Full pipeline tests — all 6 intent categories
# ---------------------------------------------------------------------------

class TestFullPipelineAllIntents:
    @pytest.mark.asyncio
    async def test_health_score_intent_returns_health_data(self):
        asm = _make_mock_assembler()
        bundle = await asm.assemble(
            user_id=_USER_ID,
            actor_role="developer",
            intent=IntentCategory.HEALTH_SCORE,
            service_id=_SVC_ID,
        )
        assert bundle.health is not None
        assert not bundle.health.is_empty
        assert bundle.health.data["overall_score"] is not None

    @pytest.mark.asyncio
    async def test_findings_intent_returns_findings_and_policy(self):
        asm = _make_mock_assembler()
        bundle = await asm.assemble(
            user_id=_USER_ID,
            actor_role="developer",
            intent=IntentCategory.FINDINGS,
            service_id=_SVC_ID,
        )
        assert bundle.findings is not None
        assert bundle.policy is not None
        assert len(bundle.findings.data["findings"]) > 0

    @pytest.mark.asyncio
    async def test_remediation_intent_returns_findings_and_policy(self):
        asm = _make_mock_assembler()
        bundle = await asm.assemble(
            user_id=_USER_ID,
            actor_role="developer",
            intent=IntentCategory.REMEDIATION,
            service_id=_SVC_ID,
        )
        assert bundle.findings is not None
        assert bundle.policy is not None

    @pytest.mark.asyncio
    async def test_release_status_intent_returns_release_and_health(self):
        asm = _make_mock_assembler()
        bundle = await asm.assemble(
            user_id=_USER_ID,
            actor_role="developer",
            intent=IntentCategory.RELEASE_STATUS,
            service_id=_SVC_ID,
        )
        assert bundle.release is not None
        assert bundle.health is not None
        assert bundle.release.data["decision"]["decision"] in (
            "APPROVE", "CONDITIONAL_APPROVE", "BLOCK"
        )

    @pytest.mark.asyncio
    async def test_policy_rules_intent_returns_rules(self):
        asm = _make_mock_assembler()
        bundle = await asm.assemble(
            user_id=_USER_ID,
            actor_role="developer",
            intent=IntentCategory.POLICY_RULES,
            service_id=_SVC_ID,
        )
        assert bundle.policy is not None
        assert len(bundle.policy.data["rules"]) > 0

    @pytest.mark.asyncio
    async def test_general_help_intent_no_db_calls(self):
        asm = _make_mock_assembler()
        bundle = await asm.assemble(
            user_id=_USER_ID,
            actor_role="developer",
            intent=IntentCategory.GENERAL_HELP,
            service_id=_SVC_ID,
        )
        asm._health.retrieve.assert_not_awaited()
        assert bundle.health is None


# ---------------------------------------------------------------------------
# Ownership scoping
# ---------------------------------------------------------------------------

class TestOwnershipScoping:
    @pytest.mark.asyncio
    async def test_unauthorized_service_returns_empty_context(self):
        asm = _make_mock_assembler(authorized=False)
        bundle = await asm.assemble(
            user_id=_USER_ID,
            actor_role="developer",
            intent=IntentCategory.HEALTH_SCORE,
            service_id=_SVC_ID,
        )
        assert bundle.is_unauthorized is True
        assert bundle.health is None

    @pytest.mark.asyncio
    async def test_unauthorized_message_is_informative(self):
        asm = _make_mock_assembler(authorized=False)
        bundle = await asm.assemble(
            user_id=_USER_ID,
            actor_role="developer",
            intent=IntentCategory.HEALTH_SCORE,
            service_id=_SVC_ID,
        )
        assert len(bundle.unauthorized_message) > 0
        assert str(_SVC_ID) in bundle.unauthorized_message

    @pytest.mark.asyncio
    async def test_authorized_user_gets_data(self):
        asm = _make_mock_assembler(authorized=True)
        bundle = await asm.assemble(
            user_id=_USER_ID,
            actor_role="developer",
            intent=IntentCategory.HEALTH_SCORE,
            service_id=_SVC_ID,
        )
        assert not bundle.is_unauthorized
        assert bundle.health is not None


# ---------------------------------------------------------------------------
# Data accuracy
# ---------------------------------------------------------------------------

class TestDataAccuracy:
    @pytest.mark.asyncio
    async def test_health_score_matches_fixture(self):
        asm = _make_mock_assembler()
        bundle = await asm.assemble(
            user_id=_USER_ID,
            actor_role="developer",
            intent=IntentCategory.HEALTH_SCORE,
            service_id=_SVC_ID,
        )
        # Fixture score for service[0] is 55.0
        assert bundle.health.data["overall_score"] == pytest.approx(55.0)

    @pytest.mark.asyncio
    async def test_findings_count_matches_fixture(self):
        asm = _make_mock_assembler()
        bundle = await asm.assemble(
            user_id=_USER_ID,
            actor_role="developer",
            intent=IntentCategory.FINDINGS,
            service_id=_SVC_ID,
        )
        # Fixture creates 10 findings per service
        assert bundle.findings.data["total_returned"] == 10

    @pytest.mark.asyncio
    async def test_release_decision_value_is_valid(self):
        asm = _make_mock_assembler()
        bundle = await asm.assemble(
            user_id=_USER_ID,
            actor_role="developer",
            intent=IntentCategory.RELEASE_STATUS,
            service_id=_SVC_ID,
        )
        decision = bundle.release.data["decision"]["decision"]
        assert decision in ("APPROVE", "CONDITIONAL_APPROVE", "BLOCK")


# ---------------------------------------------------------------------------
# Response time (2-second SLA)
# ---------------------------------------------------------------------------

class TestResponseTimeSLA:
    @pytest.mark.asyncio
    async def test_health_score_assembly_under_2_seconds(self):
        asm = _make_mock_assembler()
        start = time.monotonic()
        await asm.assemble(
            user_id=_USER_ID,
            actor_role="developer",
            intent=IntentCategory.HEALTH_SCORE,
            service_id=_SVC_ID,
        )
        elapsed = time.monotonic() - start
        # Mock calls should complete well under 2 seconds.
        assert elapsed < 2.0, f"Assembly took {elapsed:.3f}s — exceeds 2-second SLA"

    @pytest.mark.asyncio
    async def test_full_findings_assembly_under_2_seconds(self):
        asm = _make_mock_assembler()
        start = time.monotonic()
        await asm.assemble(
            user_id=_USER_ID,
            actor_role="developer",
            intent=IntentCategory.FINDINGS,
            service_id=_SVC_ID,
        )
        elapsed = time.monotonic() - start
        assert elapsed < 2.0, f"Assembly took {elapsed:.3f}s — exceeds 2-second SLA"

    @pytest.mark.asyncio
    async def test_retrieval_time_recorded_in_bundle(self):
        asm = _make_mock_assembler()
        bundle = await asm.assemble(
            user_id=_USER_ID,
            actor_role="developer",
            intent=IntentCategory.HEALTH_SCORE,
            service_id=_SVC_ID,
        )
        assert bundle.retrieval_time_ms >= 0


# ---------------------------------------------------------------------------
# to_prompt_dict integration
# ---------------------------------------------------------------------------

class TestToPromptDictIntegration:
    @pytest.mark.asyncio
    async def test_prompt_dict_includes_health_context(self):
        asm = _make_mock_assembler()
        bundle = await asm.assemble(
            user_id=_USER_ID,
            actor_role="developer",
            intent=IntentCategory.HEALTH_SCORE,
            service_id=_SVC_ID,
        )
        d = bundle.to_prompt_dict()
        assert "health_context" in d
        assert d["health_context"]["overall_score"] is not None

    @pytest.mark.asyncio
    async def test_prompt_dict_includes_intent(self):
        asm = _make_mock_assembler()
        bundle = await asm.assemble(
            user_id=_USER_ID,
            actor_role="developer",
            intent=IntentCategory.POLICY_RULES,
            service_id=_SVC_ID,
        )
        d = bundle.to_prompt_dict()
        assert d["intent"] == "policy_rules"

    @pytest.mark.asyncio
    async def test_prompt_dict_is_json_serialisable(self):
        import json
        asm = _make_mock_assembler()
        bundle = await asm.assemble(
            user_id=_USER_ID,
            actor_role="developer",
            intent=IntentCategory.FINDINGS,
            service_id=_SVC_ID,
        )
        d = bundle.to_prompt_dict()
        # Should not raise
        json_str = json.dumps(d, default=str)
        assert len(json_str) > 10
