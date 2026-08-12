"""Unit tests for Policy Guardian CRUD — Pydantic validation and service layer (WO-035)."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from forgeguard.api.schemas.policy import (
    PolicyCreate,
    PolicyRuleCreate,
    PolicyRuleUpdate,
    PolicyUpdate,
)
from forgeguard.services.policy_guardian import PolicyGuardianService
from tests.fixtures.policy_fixtures import (
    ALL_POLICIES,
    POLICY_CODE_QUALITY,
    POLICY_CODE_QUALITY_ID,
    RULES_CODE_QUALITY,
    RULE_IDS,
)


# ---------------------------------------------------------------------------
# Pydantic validation — PolicyCreate
# ---------------------------------------------------------------------------


class TestPolicyCreateValidation:
    def test_valid_policy_create(self):
        p = PolicyCreate(name="My Policy", dimension="code_quality")
        assert p.name == "My Policy"
        assert p.is_active is True

    def test_all_valid_dimensions(self):
        dims = ["code_quality", "test_coverage", "security", "documentation", "operations_readiness"]
        for d in dims:
            p = PolicyCreate(name="x", dimension=d)
            assert p.dimension == d

    def test_invalid_dimension_raises(self):
        with pytest.raises(Exception):
            PolicyCreate(name="x", dimension="bad_dimension")

    def test_name_required(self):
        with pytest.raises(Exception):
            PolicyCreate(dimension="security")

    def test_empty_name_rejected(self):
        with pytest.raises(Exception):
            PolicyCreate(name="", dimension="security")

    def test_name_too_long_rejected(self):
        with pytest.raises(Exception):
            PolicyCreate(name="x" * 256, dimension="security")


# ---------------------------------------------------------------------------
# Pydantic validation — PolicyRuleCreate
# ---------------------------------------------------------------------------


class TestPolicyRuleCreateValidation:
    def test_valid_threshold_gte(self):
        r = PolicyRuleCreate(
            name="Min Coverage",
            rule_type="threshold_gte",
            threshold_config={"numeric_value": 80},
            severity="high",
            weight=Decimal("10.0"),
        )
        assert r.rule_type == "threshold_gte"

    def test_valid_threshold_lte(self):
        r = PolicyRuleCreate(
            name="Max Complexity",
            rule_type="threshold_lte",
            threshold_config={"numeric_value": 10},
            severity="medium",
            weight=Decimal("5.0"),
        )
        assert r.threshold_config["numeric_value"] == 10

    def test_valid_threshold_eq(self):
        r = PolicyRuleCreate(
            name="Zero CVEs",
            rule_type="threshold_eq",
            threshold_config={"numeric_value": 0},
            severity="critical",
            weight=Decimal("30.0"),
        )
        assert r.severity == "critical"

    def test_threshold_missing_numeric_value_raises(self):
        with pytest.raises(Exception, match="numeric_value"):
            PolicyRuleCreate(
                name="Bad",
                rule_type="threshold_gte",
                threshold_config={"value": 80},
                severity="high",
                weight=Decimal("5.0"),
            )

    def test_threshold_non_numeric_value_raises(self):
        with pytest.raises(Exception):
            PolicyRuleCreate(
                name="Bad",
                rule_type="threshold_gte",
                threshold_config={"numeric_value": "not_a_number"},
                severity="high",
                weight=Decimal("5.0"),
            )

    def test_valid_regex_match(self):
        r = PolicyRuleCreate(
            name="Docstring",
            rule_type="regex_match",
            threshold_config={"pattern": r'"""'},
            severity="low",
            weight=Decimal("2.0"),
        )
        assert r.rule_type == "regex_match"

    def test_valid_regex_no_match(self):
        r = PolicyRuleCreate(
            name="No TODOs",
            rule_type="regex_no_match",
            threshold_config={"pattern": r"TODO|FIXME"},
            severity="low",
            weight=Decimal("1.0"),
        )
        assert r.threshold_config["pattern"] == r"TODO|FIXME"

    def test_regex_missing_pattern_raises(self):
        with pytest.raises(Exception, match="pattern"):
            PolicyRuleCreate(
                name="Bad regex",
                rule_type="regex_match",
                threshold_config={"value": "foo"},
                severity="low",
                weight=Decimal("1.0"),
            )

    def test_regex_empty_pattern_raises(self):
        with pytest.raises(Exception, match="empty"):
            PolicyRuleCreate(
                name="Bad regex",
                rule_type="regex_no_match",
                threshold_config={"pattern": ""},
                severity="low",
                weight=Decimal("1.0"),
            )

    def test_invalid_regex_pattern_raises(self):
        with pytest.raises(Exception, match="valid regex"):
            PolicyRuleCreate(
                name="Bad regex",
                rule_type="regex_match",
                threshold_config={"pattern": "[unclosed"},
                severity="low",
                weight=Decimal("1.0"),
            )

    def test_invalid_severity_raises(self):
        with pytest.raises(Exception):
            PolicyRuleCreate(
                name="Bad",
                rule_type="threshold_gte",
                threshold_config={"numeric_value": 80},
                severity="extreme",
                weight=Decimal("5.0"),
            )

    def test_invalid_rule_type_raises(self):
        with pytest.raises(Exception):
            PolicyRuleCreate(
                name="Bad",
                rule_type="unknown_type",
                threshold_config={"numeric_value": 80},
                severity="high",
                weight=Decimal("5.0"),
            )

    def test_weight_below_zero_raises(self):
        with pytest.raises(Exception):
            PolicyRuleCreate(
                name="Bad",
                rule_type="threshold_gte",
                threshold_config={"numeric_value": 80},
                severity="high",
                weight=Decimal("-1.0"),
            )

    def test_weight_above_100_raises(self):
        with pytest.raises(Exception):
            PolicyRuleCreate(
                name="Bad",
                rule_type="threshold_gte",
                threshold_config={"numeric_value": 80},
                severity="high",
                weight=Decimal("101.0"),
            )

    def test_weight_exactly_100_valid(self):
        r = PolicyRuleCreate(
            name="Full Weight",
            rule_type="threshold_gte",
            threshold_config={"numeric_value": 80},
            severity="high",
            weight=Decimal("100.0"),
        )
        assert r.weight == Decimal("100.0")

    def test_weight_zero_valid(self):
        r = PolicyRuleCreate(
            name="Zero Weight",
            rule_type="threshold_gte",
            threshold_config={"numeric_value": 80},
            severity="high",
            weight=Decimal("0.0"),
        )
        assert r.weight == Decimal("0.0")


# ---------------------------------------------------------------------------
# PolicyGuardianService — unit tests with mocked repo
# ---------------------------------------------------------------------------


def _make_svc(repo_mock: Any) -> PolicyGuardianService:
    return PolicyGuardianService(repo=repo_mock, audit_service=None)


class TestPolicyGuardianServiceListPolicies:
    @pytest.mark.asyncio
    async def test_list_returns_items_and_total(self):
        repo = MagicMock()
        repo.list_with_rule_counts = AsyncMock(return_value=list(ALL_POLICIES))
        repo.count_policies = AsyncMock(return_value=3)
        svc = _make_svc(repo)

        result = await svc.list_policies(limit=50)
        assert result["total_count"] == 3
        assert len(result["items"]) == 3
        assert result["next_cursor"] is None

    @pytest.mark.asyncio
    async def test_list_produces_next_cursor_when_more(self):
        # Return limit+1 rows to trigger has_more
        rows = list(ALL_POLICIES) + [dict(ALL_POLICIES[0])]
        repo = MagicMock()
        repo.list_with_rule_counts = AsyncMock(return_value=rows)
        repo.count_policies = AsyncMock(return_value=10)
        svc = _make_svc(repo)

        result = await svc.list_policies(limit=3)
        assert result["next_cursor"] is not None
        assert len(result["items"]) == 3


class TestPolicyGuardianServiceCreatePolicy:
    @pytest.mark.asyncio
    async def test_create_policy_returns_created_row(self):
        repo = MagicMock()
        repo.create = AsyncMock(return_value=dict(POLICY_CODE_QUALITY))
        svc = _make_svc(repo)

        result = await svc.create_policy(
            {"name": "My Policy", "dimension": "code_quality", "is_active": True},
            actor_id=str(uuid.uuid4()),
            actor_role="platform_admin",
        )
        assert result["name"] == POLICY_CODE_QUALITY["name"]
        repo.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_policy_calls_audit(self):
        repo = MagicMock()
        repo.create = AsyncMock(return_value=dict(POLICY_CODE_QUALITY))
        audit = MagicMock()
        audit.log_event = AsyncMock()
        svc = PolicyGuardianService(repo, audit)

        await svc.create_policy(
            {"name": "My Policy", "dimension": "code_quality"},
            actor_id="actor-1",
            actor_role="platform_admin",
        )
        audit.log_event.assert_called_once()
        call_kwargs = audit.log_event.call_args.kwargs
        assert call_kwargs["action"] == "policy.created"


class TestPolicyGuardianServiceUpdatePolicy:
    @pytest.mark.asyncio
    async def test_update_returns_none_for_missing_policy(self):
        repo = MagicMock()
        repo.get_by_id = AsyncMock(return_value=None)
        svc = _make_svc(repo)

        result = await svc.update_policy(
            uuid.uuid4(), {"name": "New"}, actor_id="a", actor_role="platform_admin"
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_update_raises_on_version_mismatch(self):
        repo = MagicMock()
        repo.get_by_id = AsyncMock(return_value=dict(POLICY_CODE_QUALITY))
        svc = _make_svc(repo)

        with pytest.raises(ValueError, match="[Vv]ersion"):
            await svc.update_policy(
                POLICY_CODE_QUALITY_ID,
                {"name": "New"},
                actor_id="a",
                actor_role="platform_admin",
                expected_version=99,
            )

    @pytest.mark.asyncio
    async def test_update_increments_version(self):
        updated_row = {**POLICY_CODE_QUALITY, "version": 2}
        repo = MagicMock()
        repo.get_by_id = AsyncMock(return_value=dict(POLICY_CODE_QUALITY))
        repo.update = AsyncMock(return_value=updated_row)
        repo.increment_version = AsyncMock(return_value=updated_row)
        svc = _make_svc(repo)

        result = await svc.update_policy(
            POLICY_CODE_QUALITY_ID,
            {"name": "Updated"},
            actor_id="a",
            actor_role="platform_admin",
        )
        repo.increment_version.assert_called_once()


class TestPolicyGuardianServiceRuleCRUD:
    @pytest.mark.asyncio
    async def test_create_rule_returns_none_for_missing_policy(self):
        repo = MagicMock()
        repo.get_by_id = AsyncMock(return_value=None)
        svc = _make_svc(repo)

        result = await svc.create_rule(
            uuid.uuid4(),
            {
                "name": "r",
                "rule_type": "threshold_gte",
                "threshold_config": {"numeric_value": 80},
                "severity": "high",
                "weight": 10.0,
            },
            actor_id="a",
            actor_role="platform_admin",
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_create_rule_calls_audit(self):
        repo = MagicMock()
        repo.get_by_id = AsyncMock(return_value=dict(POLICY_CODE_QUALITY))
        repo.create_rule = AsyncMock(return_value=dict(RULES_CODE_QUALITY[0]))
        audit = MagicMock()
        audit.log_event = AsyncMock()
        svc = PolicyGuardianService(repo, audit)

        await svc.create_rule(
            POLICY_CODE_QUALITY_ID,
            {
                "name": "r",
                "rule_type": "threshold_gte",
                "threshold_config": {"numeric_value": 80},
                "severity": "high",
                "weight": 10.0,
            },
            actor_id="a",
            actor_role="platform_admin",
        )
        audit.log_event.assert_called_once()
        assert audit.log_event.call_args.kwargs["action"] == "policy_rule.created"

    @pytest.mark.asyncio
    async def test_toggle_rule_returns_none_when_rule_not_found(self):
        repo = MagicMock()
        repo.get_rule_by_id = AsyncMock(return_value=None)
        svc = _make_svc(repo)

        result = await svc.toggle_rule(
            POLICY_CODE_QUALITY_ID, uuid.uuid4(), actor_id="a", actor_role="platform_admin"
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_toggle_rule_returns_none_for_wrong_policy(self):
        rule = dict(RULES_CODE_QUALITY[0])
        repo = MagicMock()
        repo.get_rule_by_id = AsyncMock(return_value=rule)
        svc = _make_svc(repo)

        result = await svc.toggle_rule(
            uuid.uuid4(),  # wrong policy_id
            rule["id"],
            actor_id="a",
            actor_role="platform_admin",
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_toggle_rule_flips_active(self):
        rule = {**RULES_CODE_QUALITY[0], "is_active": True}
        toggled = {**rule, "is_active": False}
        repo = MagicMock()
        repo.get_rule_by_id = AsyncMock(return_value=rule)
        repo.toggle_rule = AsyncMock(return_value=toggled)
        svc = _make_svc(repo)

        result = await svc.toggle_rule(
            POLICY_CODE_QUALITY_ID, rule["id"], actor_id="a", actor_role="platform_admin"
        )
        assert result["is_active"] is False
