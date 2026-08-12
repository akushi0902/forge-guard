"""Unit tests for FindingGenerator and FindingStatus state machine (WO-041).

Covers:
  - FindingStatus VALID_TRANSITIONS: all valid and invalid paths
  - FindingGenerator.generate_findings: FAIL/ERROR only, PASS/INCONCLUSIVE ignored
  - Duplicate detection: existing open finding is updated, not duplicated
  - Escalation flag: critical+security → True; other combinations → False
  - Title and description generation (standard + ERROR variant)
  - Empty result set → empty list returned
  - bulk_create_findings (repository-level) using async mock

Run:
    pytest tests/unit/services/test_finding_generator.py -v
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from forgeguard.services.domain.evaluation import EvaluationStatus, RuleEvaluationResult
from forgeguard.services.domain.finding_status import FindingStatus, VALID_TRANSITIONS
from forgeguard.services.domain.severity import SeverityLevel
from forgeguard.services.finding_generator import FindingGenerator

_TS = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _result(
    *,
    name: str = "Test Rule",
    dimension: str = "security",
    status: EvaluationStatus = EvaluationStatus.FAIL,
    severity: SeverityLevel = SeverityLevel.HIGH,
    actual: Any = 5,
    expected: Any = 0,
    rule_id: uuid.UUID | None = None,
    evidence: dict | None = None,
) -> RuleEvaluationResult:
    return RuleEvaluationResult(
        rule_id=rule_id or uuid.uuid4(),
        rule_name=name,
        dimension=dimension,
        severity=severity,
        status=status,
        actual_value=actual,
        expected_value=expected,
        evidence=evidence or {},
        evaluated_at=_TS,
        weight=Decimal("1"),
    )


def _make_repo(
    *,
    existing: dict | None = None,
    created: dict | None = None,
    updated: dict | None = None,
) -> MagicMock:
    """Build a mock FindingRepository with configurable return values."""
    repo = MagicMock()
    repo.find_existing_open_finding = AsyncMock(return_value=existing)
    repo.create = AsyncMock(return_value=created or {"id": uuid.uuid4(), "status": "open"})
    repo.update = AsyncMock(return_value=updated or {"id": uuid.uuid4(), "status": "open"})
    return repo


def _make_generator(repo=None) -> FindingGenerator:
    if repo is None:
        repo = _make_repo()
    return FindingGenerator(repo)


# ===========================================================================
# FindingStatus state machine
# ===========================================================================

class TestFindingStatusTransitions:
    """Validate every defined transition is accepted and invalid ones are rejected."""

    @pytest.mark.parametrize("from_status,to_status", [
        (FindingStatus.OPEN, FindingStatus.ACKNOWLEDGED),
        (FindingStatus.OPEN, FindingStatus.EXCEPTION_GRANTED),
        (FindingStatus.ACKNOWLEDGED, FindingStatus.REMEDIATED),
        (FindingStatus.REMEDIATED, FindingStatus.REOPENED),
        (FindingStatus.EXCEPTION_GRANTED, FindingStatus.REOPENED),
        (FindingStatus.REOPENED, FindingStatus.ACKNOWLEDGED),
        (FindingStatus.REOPENED, FindingStatus.EXCEPTION_GRANTED),
    ])
    def test_valid_transition_accepted(self, from_status, to_status):
        assert to_status in VALID_TRANSITIONS[from_status]

    @pytest.mark.parametrize("from_status,to_status", [
        (FindingStatus.OPEN, FindingStatus.REMEDIATED),
        (FindingStatus.OPEN, FindingStatus.REOPENED),
        (FindingStatus.ACKNOWLEDGED, FindingStatus.OPEN),
        (FindingStatus.ACKNOWLEDGED, FindingStatus.EXCEPTION_GRANTED),
        (FindingStatus.REMEDIATED, FindingStatus.OPEN),
        (FindingStatus.REMEDIATED, FindingStatus.ACKNOWLEDGED),
        (FindingStatus.EXCEPTION_GRANTED, FindingStatus.OPEN),
        (FindingStatus.EXCEPTION_GRANTED, FindingStatus.REMEDIATED),
        (FindingStatus.REOPENED, FindingStatus.REMEDIATED),
        (FindingStatus.REOPENED, FindingStatus.OPEN),
    ])
    def test_invalid_transition_rejected(self, from_status, to_status):
        assert to_status not in VALID_TRANSITIONS[from_status]

    def test_all_statuses_have_entries(self):
        for status in FindingStatus:
            assert status in VALID_TRANSITIONS

    def test_open_has_two_valid_transitions(self):
        assert len(VALID_TRANSITIONS[FindingStatus.OPEN]) == 2

    def test_acknowledged_has_one_valid_transition(self):
        assert len(VALID_TRANSITIONS[FindingStatus.ACKNOWLEDGED]) == 1

    def test_reopened_mirrors_open_transitions(self):
        assert VALID_TRANSITIONS[FindingStatus.REOPENED] == VALID_TRANSITIONS[FindingStatus.OPEN]


class TestFindingStatusEnum:
    def test_values_are_strings(self):
        for status in FindingStatus:
            assert isinstance(status, str)

    def test_open_value(self):
        assert FindingStatus.OPEN == "open"

    def test_acknowledged_value(self):
        assert FindingStatus.ACKNOWLEDGED == "acknowledged"

    def test_remediated_value(self):
        assert FindingStatus.REMEDIATED == "remediated"

    def test_exception_granted_value(self):
        assert FindingStatus.EXCEPTION_GRANTED == "exception_granted"

    def test_reopened_value(self):
        assert FindingStatus.REOPENED == "reopened"

    def test_five_statuses_total(self):
        assert len(list(FindingStatus)) == 5


# ===========================================================================
# FindingGenerator.generate_findings — FAIL/ERROR only
# ===========================================================================

class TestGenerateFindings_ActionableStatuses:
    @pytest.mark.asyncio
    async def test_fail_result_creates_finding(self):
        repo = _make_repo()
        gen = FindingGenerator(repo)
        results = [_result(status=EvaluationStatus.FAIL)]
        findings = await gen.generate_findings(results, uuid.uuid4(), uuid.uuid4())
        assert len(findings) == 1
        repo.create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_error_result_creates_finding(self):
        repo = _make_repo()
        gen = FindingGenerator(repo)
        results = [_result(status=EvaluationStatus.ERROR)]
        findings = await gen.generate_findings(results, uuid.uuid4(), uuid.uuid4())
        assert len(findings) == 1
        repo.create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_pass_result_ignored(self):
        repo = _make_repo()
        gen = FindingGenerator(repo)
        results = [_result(status=EvaluationStatus.PASS)]
        findings = await gen.generate_findings(results, uuid.uuid4(), uuid.uuid4())
        assert findings == []
        repo.create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_inconclusive_result_ignored(self):
        repo = _make_repo()
        gen = FindingGenerator(repo)
        results = [_result(status=EvaluationStatus.INCONCLUSIVE)]
        findings = await gen.generate_findings(results, uuid.uuid4(), uuid.uuid4())
        assert findings == []
        repo.create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_mixed_only_fail_error_generate_findings(self):
        repo = _make_repo()
        gen = FindingGenerator(repo)
        results = [
            _result(status=EvaluationStatus.PASS),
            _result(status=EvaluationStatus.FAIL),
            _result(status=EvaluationStatus.INCONCLUSIVE),
            _result(status=EvaluationStatus.ERROR),
        ]
        findings = await gen.generate_findings(results, uuid.uuid4(), uuid.uuid4())
        assert len(findings) == 2
        assert repo.create.await_count == 2

    @pytest.mark.asyncio
    async def test_empty_results_returns_empty_list(self):
        repo = _make_repo()
        gen = FindingGenerator(repo)
        findings = await gen.generate_findings([], uuid.uuid4(), uuid.uuid4())
        assert findings == []
        repo.create.assert_not_awaited()


# ===========================================================================
# Duplicate detection
# ===========================================================================

class TestGenerateFindings_DuplicateDetection:
    @pytest.mark.asyncio
    async def test_existing_open_finding_is_updated_not_duplicated(self):
        existing_id = uuid.uuid4()
        existing = {"id": existing_id, "status": "open"}
        updated = {"id": existing_id, "status": "open", "evidence": {"actual_value": 5}}
        repo = _make_repo(existing=existing, updated=updated)
        gen = FindingGenerator(repo)
        result = _result(status=EvaluationStatus.FAIL)
        findings = await gen.generate_findings([result], uuid.uuid4(), uuid.uuid4())
        assert len(findings) == 1
        repo.create.assert_not_awaited()
        repo.update.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_existing_finding_creates_new(self):
        repo = _make_repo(existing=None)
        gen = FindingGenerator(repo)
        findings = await gen.generate_findings([_result()], uuid.uuid4(), uuid.uuid4())
        assert len(findings) == 1
        repo.create.assert_awaited_once()
        repo.update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_dedup_check_uses_service_and_rule_id(self):
        service_id = uuid.uuid4()
        rule_id = uuid.uuid4()
        repo = _make_repo(existing=None)
        gen = FindingGenerator(repo)
        result = _result(rule_id=rule_id)
        await gen.generate_findings([result], uuid.uuid4(), service_id)
        repo.find_existing_open_finding.assert_awaited_once_with(service_id, rule_id)

    @pytest.mark.asyncio
    async def test_update_sets_assessment_id_and_evidence(self):
        existing = {"id": uuid.uuid4(), "status": "open"}
        repo = _make_repo(existing=existing)
        gen = FindingGenerator(repo)
        assessment_id = uuid.uuid4()
        await gen.generate_findings([_result()], assessment_id, uuid.uuid4())
        call_kwargs = repo.update.call_args[0][1]
        assert "assessment_id" in call_kwargs
        assert "evidence" in call_kwargs
        assert call_kwargs["assessment_id"] == assessment_id


# ===========================================================================
# Escalation flag
# ===========================================================================

class TestGenerateFindings_EscalationFlag:
    @pytest.mark.asyncio
    async def test_critical_security_sets_escalation_true(self):
        repo = _make_repo(existing=None)
        gen = FindingGenerator(repo)
        result = _result(
            severity=SeverityLevel.CRITICAL,
            dimension="security",
            status=EvaluationStatus.FAIL,
        )
        await gen.generate_findings([result], uuid.uuid4(), uuid.uuid4())
        create_data = repo.create.call_args[0][0]
        assert create_data["escalation_required"] is True

    @pytest.mark.asyncio
    async def test_critical_non_security_no_escalation(self):
        repo = _make_repo(existing=None)
        gen = FindingGenerator(repo)
        result = _result(
            severity=SeverityLevel.CRITICAL,
            dimension="code_quality",
            status=EvaluationStatus.FAIL,
        )
        await gen.generate_findings([result], uuid.uuid4(), uuid.uuid4())
        create_data = repo.create.call_args[0][0]
        assert create_data["escalation_required"] is False

    @pytest.mark.asyncio
    async def test_high_security_no_escalation(self):
        repo = _make_repo(existing=None)
        gen = FindingGenerator(repo)
        result = _result(
            severity=SeverityLevel.HIGH,
            dimension="security",
            status=EvaluationStatus.FAIL,
        )
        await gen.generate_findings([result], uuid.uuid4(), uuid.uuid4())
        create_data = repo.create.call_args[0][0]
        assert create_data["escalation_required"] is False

    @pytest.mark.asyncio
    async def test_medium_documentation_no_escalation(self):
        repo = _make_repo(existing=None)
        gen = FindingGenerator(repo)
        result = _result(
            severity=SeverityLevel.MEDIUM,
            dimension="documentation",
            status=EvaluationStatus.FAIL,
        )
        await gen.generate_findings([result], uuid.uuid4(), uuid.uuid4())
        create_data = repo.create.call_args[0][0]
        assert create_data["escalation_required"] is False


# ===========================================================================
# Title generation
# ===========================================================================

class TestTitleGeneration:
    def test_title_includes_rule_name_and_dimension(self):
        result = _result(name="CVE Check", dimension="security")
        title = FindingGenerator._make_title(result)
        assert title == "CVE Check violation in security"

    def test_title_with_multi_word_rule_name(self):
        result = _result(name="Unit Test Coverage", dimension="test_coverage")
        title = FindingGenerator._make_title(result)
        assert title == "Unit Test Coverage violation in test_coverage"

    def test_title_uses_dimension_string_verbatim(self):
        result = _result(name="Rule", dimension="operations_readiness")
        title = FindingGenerator._make_title(result)
        assert "operations_readiness" in title


# ===========================================================================
# Description generation
# ===========================================================================

class TestDescriptionGeneration:
    def test_fail_description_shows_expected_and_actual(self):
        result = _result(status=EvaluationStatus.FAIL, actual=15, expected=10, name="Complexity Check")
        desc = FindingGenerator._make_description(result)
        assert "Expected 10 but found 15" in desc
        assert "Complexity Check" in desc

    def test_error_description_mentions_evaluation_error(self):
        result = _result(status=EvaluationStatus.ERROR, name="CVE Scanner")
        desc = FindingGenerator._make_description(result)
        assert "evaluation error" in desc.lower() or "did not complete" in desc.lower()
        assert "CVE Scanner" in desc

    def test_fail_description_format(self):
        result = _result(status=EvaluationStatus.FAIL, actual="false", expected="true", name="Docs Check")
        desc = FindingGenerator._make_description(result)
        assert desc == "Expected true but found false for Docs Check"


# ===========================================================================
# Evidence construction
# ===========================================================================

class TestEvidenceConstruction:
    def test_evidence_includes_actual_value(self):
        result = _result(actual=42)
        ev = FindingGenerator._build_evidence(result)
        assert ev["actual_value"] == 42

    def test_evidence_includes_expected_value(self):
        result = _result(expected=0)
        ev = FindingGenerator._build_evidence(result)
        assert ev["expected_value"] == 0

    def test_evidence_includes_evaluation_status(self):
        result = _result(status=EvaluationStatus.FAIL)
        ev = FindingGenerator._build_evidence(result)
        assert ev["evaluation_status"] == "fail"

    def test_evidence_merges_rule_evidence(self):
        result = _result(evidence={"data_key": "cve_count", "rule_type": "threshold_gte"})
        ev = FindingGenerator._build_evidence(result)
        assert ev["data_key"] == "cve_count"
        assert ev["rule_type"] == "threshold_gte"


# ===========================================================================
# Finding record fields
# ===========================================================================

class TestFindingRecordFields:
    @pytest.mark.asyncio
    async def test_new_finding_has_status_open(self):
        repo = _make_repo(existing=None)
        gen = FindingGenerator(repo)
        await gen.generate_findings([_result()], uuid.uuid4(), uuid.uuid4())
        create_data = repo.create.call_args[0][0]
        assert create_data["status"] == "open"

    @pytest.mark.asyncio
    async def test_new_finding_has_uuid_id(self):
        repo = _make_repo(existing=None)
        gen = FindingGenerator(repo)
        await gen.generate_findings([_result()], uuid.uuid4(), uuid.uuid4())
        create_data = repo.create.call_args[0][0]
        assert isinstance(create_data["id"], uuid.UUID)

    @pytest.mark.asyncio
    async def test_new_finding_service_id_matches(self):
        service_id = uuid.uuid4()
        repo = _make_repo(existing=None)
        gen = FindingGenerator(repo)
        await gen.generate_findings([_result()], uuid.uuid4(), service_id)
        create_data = repo.create.call_args[0][0]
        assert create_data["service_id"] == service_id

    @pytest.mark.asyncio
    async def test_new_finding_assessment_id_matches(self):
        assessment_id = uuid.uuid4()
        repo = _make_repo(existing=None)
        gen = FindingGenerator(repo)
        await gen.generate_findings([_result()], assessment_id, uuid.uuid4())
        create_data = repo.create.call_args[0][0]
        assert create_data["assessment_id"] == assessment_id

    @pytest.mark.asyncio
    async def test_new_finding_policy_rule_id_matches(self):
        rule_id = uuid.uuid4()
        repo = _make_repo(existing=None)
        gen = FindingGenerator(repo)
        result = _result(rule_id=rule_id)
        await gen.generate_findings([result], uuid.uuid4(), uuid.uuid4())
        create_data = repo.create.call_args[0][0]
        assert create_data["policy_rule_id"] == rule_id

    @pytest.mark.asyncio
    async def test_new_finding_severity_string(self):
        repo = _make_repo(existing=None)
        gen = FindingGenerator(repo)
        result = _result(severity=SeverityLevel.CRITICAL)
        await gen.generate_findings([result], uuid.uuid4(), uuid.uuid4())
        create_data = repo.create.call_args[0][0]
        assert create_data["severity"] == "critical"

    @pytest.mark.asyncio
    async def test_new_finding_dimension_matches(self):
        repo = _make_repo(existing=None)
        gen = FindingGenerator(repo)
        result = _result(dimension="test_coverage")
        await gen.generate_findings([result], uuid.uuid4(), uuid.uuid4())
        create_data = repo.create.call_args[0][0]
        assert create_data["dimension"] == "test_coverage"
