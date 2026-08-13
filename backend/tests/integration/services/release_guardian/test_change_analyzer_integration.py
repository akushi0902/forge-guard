"""Integration tests for ChangeAnalyzer using MockChangeDataProvider (WO-045).

Tests all 5 payment service demo scenarios end-to-end.
No GitHub API or database connection required.
"""

from __future__ import annotations

import uuid

import pytest

from forgeguard.services.release_guardian.change_analyzer import ChangeAnalyzer
from forgeguard.services.release_guardian.providers_mock import MockChangeDataProvider


SERVICE_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


class TestScenario1SmallSafe:
    """Small safe change: 2 files, tests included, no deps."""

    @pytest.mark.asyncio
    async def test_returns_change_analysis_result(self):
        provider = MockChangeDataProvider("small_safe_change")
        analyzer = ChangeAnalyzer(provider)
        result = await analyzer.analyze(SERVICE_ID, commit_sha="abc123")
        assert result is not None

    @pytest.mark.asyncio
    async def test_has_expected_structure(self):
        provider = MockChangeDataProvider("small_safe_change")
        analyzer = ChangeAnalyzer(provider)
        result = await analyzer.analyze(SERVICE_ID, commit_sha="abc123")
        assert result.complexity is not None
        assert result.coverage is not None
        assert result.dependencies is not None
        assert result.security is not None
        assert result.metadata is not None

    @pytest.mark.asyncio
    async def test_small_files_changed(self):
        provider = MockChangeDataProvider("small_safe_change")
        analyzer = ChangeAnalyzer(provider)
        result = await analyzer.analyze(SERVICE_ID, commit_sha="abc123")
        assert result.complexity.files_changed == 2

    @pytest.mark.asyncio
    async def test_has_new_tests(self):
        provider = MockChangeDataProvider("small_safe_change")
        analyzer = ChangeAnalyzer(provider)
        result = await analyzer.analyze(SERVICE_ID, commit_sha="abc123")
        assert result.coverage.has_new_tests is True

    @pytest.mark.asyncio
    async def test_no_security_issues(self):
        provider = MockChangeDataProvider("small_safe_change")
        analyzer = ChangeAnalyzer(provider)
        result = await analyzer.analyze(SERVICE_ID, commit_sha="abc123")
        assert result.security.secrets_detected == 0
        assert result.security.sql_patterns_detected == 0

    @pytest.mark.asyncio
    async def test_no_dependency_changes(self):
        provider = MockChangeDataProvider("small_safe_change")
        analyzer = ChangeAnalyzer(provider)
        result = await analyzer.analyze(SERVICE_ID, commit_sha="abc123")
        assert result.dependencies.dependencies_added == []
        assert result.dependencies.known_cves == []

    @pytest.mark.asyncio
    async def test_metadata_provider_name(self):
        provider = MockChangeDataProvider("small_safe_change")
        analyzer = ChangeAnalyzer(provider)
        result = await analyzer.analyze(SERVICE_ID, commit_sha="abc123")
        assert "Mock" in result.metadata.provider

    @pytest.mark.asyncio
    async def test_no_incomplete_dimensions(self):
        provider = MockChangeDataProvider("small_safe_change")
        analyzer = ChangeAnalyzer(provider)
        result = await analyzer.analyze(SERVICE_ID, commit_sha="abc123")
        assert result.metadata.incomplete_dimensions == []


class TestScenario2LargeRisky:
    """Large risky change: many files, high complexity, no tests."""

    @pytest.mark.asyncio
    async def test_high_files_changed(self):
        provider = MockChangeDataProvider("large_risky_change")
        analyzer = ChangeAnalyzer(provider)
        result = await analyzer.analyze(SERVICE_ID, commit_sha="def456")
        assert result.complexity.files_changed >= 3

    @pytest.mark.asyncio
    async def test_high_complexity_delta(self):
        provider = MockChangeDataProvider("large_risky_change")
        analyzer = ChangeAnalyzer(provider)
        result = await analyzer.analyze(SERVICE_ID, commit_sha="def456")
        assert result.complexity.cyclomatic_complexity_delta > 0.0

    @pytest.mark.asyncio
    async def test_high_churn_score(self):
        provider = MockChangeDataProvider("large_risky_change")
        analyzer = ChangeAnalyzer(provider)
        result = await analyzer.analyze(SERVICE_ID, commit_sha="def456")
        assert result.complexity.churn_score > 0.0

    @pytest.mark.asyncio
    async def test_no_tests_negative_coverage(self):
        provider = MockChangeDataProvider("large_risky_change")
        analyzer = ChangeAnalyzer(provider)
        result = await analyzer.analyze(SERVICE_ID, commit_sha="def456")
        # No test files in this scenario
        assert result.coverage.has_new_tests is False


class TestScenario3DependencyHeavy:
    """Dependency-heavy change: 10 dep updates, 2 CVEs."""

    @pytest.mark.asyncio
    async def test_dependencies_updated(self):
        provider = MockChangeDataProvider("dependency_heavy_change")
        analyzer = ChangeAnalyzer(provider)
        result = await analyzer.analyze(SERVICE_ID, commit_sha="fed321")
        assert len(result.dependencies.dependencies_updated) > 0 or \
               len(result.dependencies.dependencies_added) > 0

    @pytest.mark.asyncio
    async def test_result_is_serializable(self):
        provider = MockChangeDataProvider("dependency_heavy_change")
        analyzer = ChangeAnalyzer(provider)
        result = await analyzer.analyze(SERVICE_ID, commit_sha="fed321")
        # Must be serializable to JSONB
        data = result.model_dump()
        assert isinstance(data, dict)
        assert "complexity" in data
        assert "dependencies" in data


class TestScenario4SecuritySensitive:
    """Security-sensitive change: secrets and SQL patterns detected."""

    @pytest.mark.asyncio
    async def test_secrets_detected(self):
        provider = MockChangeDataProvider("security_sensitive_change")
        analyzer = ChangeAnalyzer(provider)
        result = await analyzer.analyze(SERVICE_ID, commit_sha="a1b2c3")
        assert result.security.secrets_detected >= 1

    @pytest.mark.asyncio
    async def test_sql_patterns_detected(self):
        provider = MockChangeDataProvider("security_sensitive_change")
        analyzer = ChangeAnalyzer(provider)
        result = await analyzer.analyze(SERVICE_ID, commit_sha="a1b2c3")
        assert result.security.sql_patterns_detected >= 1

    @pytest.mark.asyncio
    async def test_unsafe_deserialization_detected(self):
        provider = MockChangeDataProvider("security_sensitive_change")
        analyzer = ChangeAnalyzer(provider)
        result = await analyzer.analyze(SERVICE_ID, commit_sha="a1b2c3")
        assert result.security.unsafe_deserialization_detected >= 1


class TestScenario5TestOnly:
    """Test-only change: only test files modified."""

    @pytest.mark.asyncio
    async def test_all_test_files(self):
        provider = MockChangeDataProvider("test_only_change")
        analyzer = ChangeAnalyzer(provider)
        result = await analyzer.analyze(SERVICE_ID, commit_sha="f0e1d2")
        assert result.coverage.test_files_changed >= 1

    @pytest.mark.asyncio
    async def test_has_new_tests(self):
        provider = MockChangeDataProvider("test_only_change")
        analyzer = ChangeAnalyzer(provider)
        result = await analyzer.analyze(SERVICE_ID, commit_sha="f0e1d2")
        assert result.coverage.has_new_tests is True

    @pytest.mark.asyncio
    async def test_positive_coverage_delta(self):
        provider = MockChangeDataProvider("test_only_change")
        analyzer = ChangeAnalyzer(provider)
        result = await analyzer.analyze(SERVICE_ID, commit_sha="f0e1d2")
        # Test-only change should have positive or neutral coverage delta
        assert result.coverage.estimated_coverage_delta >= 0.0

    @pytest.mark.asyncio
    async def test_no_security_issues(self):
        provider = MockChangeDataProvider("test_only_change")
        analyzer = ChangeAnalyzer(provider)
        result = await analyzer.analyze(SERVICE_ID, commit_sha="f0e1d2")
        assert result.security.secrets_detected == 0


class TestChangeAnalyzerEdgeCases:
    @pytest.mark.asyncio
    async def test_raises_without_commit_or_pr(self):
        provider = MockChangeDataProvider("small_safe_change")
        analyzer = ChangeAnalyzer(provider)
        with pytest.raises(ValueError, match="commit_sha or pr_reference"):
            await analyzer.analyze(SERVICE_ID)

    @pytest.mark.asyncio
    async def test_pr_reference_accepted(self):
        provider = MockChangeDataProvider("small_safe_change")
        analyzer = ChangeAnalyzer(provider)
        result = await analyzer.analyze(SERVICE_ID, pr_reference="42")
        assert result is not None

    @pytest.mark.asyncio
    async def test_analysis_duration_recorded(self):
        provider = MockChangeDataProvider("small_safe_change")
        analyzer = ChangeAnalyzer(provider)
        result = await analyzer.analyze(SERVICE_ID, commit_sha="abc123")
        assert result.metadata.analysis_duration_ms >= 0

    @pytest.mark.asyncio
    async def test_result_serializable_to_dict(self):
        provider = MockChangeDataProvider("small_safe_change")
        analyzer = ChangeAnalyzer(provider)
        result = await analyzer.analyze(SERVICE_ID, commit_sha="abc123")
        data = result.model_dump()
        assert set(data.keys()) == {"complexity", "coverage", "dependencies", "security", "metadata"}
