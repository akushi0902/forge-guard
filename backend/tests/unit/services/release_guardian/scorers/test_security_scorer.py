"""Unit tests for SecurityScorer — secrets short-circuit and other pattern scoring."""

from __future__ import annotations

import pytest

from forgeguard.services.release_guardian.models import SecurityMetrics
from forgeguard.services.release_guardian.scorers.security_scorer import SecurityScorer


def _metrics(secrets=0, sql=0, deser=0, config_changes=None):
    return SecurityMetrics(
        secrets_detected=secrets,
        sql_patterns_detected=sql,
        unsafe_deserialization_detected=deser,
        security_config_changes=config_changes or [],
    )


@pytest.fixture
def scorer():
    return SecurityScorer()


class TestSecretsShortCircuit:
    def test_one_secret_returns_100_and_critical(self, scorer):
        score, _, is_critical = scorer.score(_metrics(secrets=1))
        assert score == 100
        assert is_critical is True

    def test_multiple_secrets_returns_100_and_critical(self, scorer):
        score, _, is_critical = scorer.score(_metrics(secrets=5))
        assert score == 100
        assert is_critical is True

    def test_no_secrets_not_critical(self, scorer):
        _, _, is_critical = scorer.score(_metrics())
        assert is_critical is False

    def test_secrets_short_circuit_ignores_other_metrics(self, scorer):
        score, factors, is_critical = scorer.score(_metrics(secrets=1, sql=3, deser=2))
        assert score == 100
        assert is_critical is True
        # Only the secrets factor should be in the list (short-circuit)
        assert len(factors) == 1
        assert factors[0].metric_name == "secrets_detected"


class TestSQLPatterns:
    def test_zero_sql_patterns(self, scorer):
        score, _, _ = scorer.score(_metrics(sql=0))
        assert score == 0

    def test_one_sql_pattern_adds_25(self, scorer):
        score, _, _ = scorer.score(_metrics(sql=1))
        assert score == 25

    def test_two_sql_patterns_adds_50(self, scorer):
        score, _, _ = scorer.score(_metrics(sql=2))
        assert score == 50

    def test_four_sql_patterns_capped_at_100(self, scorer):
        score, _, _ = scorer.score(_metrics(sql=4))
        assert score == 100

    def test_many_sql_patterns_capped_at_100(self, scorer):
        score, _, _ = scorer.score(_metrics(sql=10))
        assert score == 100


class TestUnsafeDeserialization:
    def test_zero_deserialization_no_contribution(self, scorer):
        score, _, _ = scorer.score(_metrics(deser=0))
        assert score == 0

    def test_one_deserialization_adds_30(self, scorer):
        score, _, _ = scorer.score(_metrics(deser=1))
        assert score == 30

    def test_three_deserialization_adds_90(self, scorer):
        score, _, _ = scorer.score(_metrics(deser=3))
        assert score == 90

    def test_four_deserialization_capped_at_100(self, scorer):
        score, _, _ = scorer.score(_metrics(deser=4))
        assert score == 100


class TestSecurityConfigChanges:
    def test_no_config_changes(self, scorer):
        score, _, _ = scorer.score(_metrics(config_changes=[]))
        assert score == 0

    def test_one_config_change_adds_5(self, scorer):
        score, _, _ = scorer.score(_metrics(config_changes=["auth.yaml"]))
        assert score == 5

    def test_four_config_changes_adds_20(self, scorer):
        score, _, _ = scorer.score(_metrics(config_changes=["a", "b", "c", "d"]))
        assert score == 20

    def test_config_changes_capped_at_20(self, scorer):
        score, _, _ = scorer.score(_metrics(config_changes=["a", "b", "c", "d", "e"]))
        assert score == 20


class TestCombinedNonCritical:
    def test_sql_plus_deser_combined(self, scorer):
        # 1 SQL (25) + 1 deser (30) = 55
        score, _, is_critical = scorer.score(_metrics(sql=1, deser=1))
        assert score == 55
        assert is_critical is False

    def test_all_non_secrets_capped_at_100(self, scorer):
        score, _, _ = scorer.score(_metrics(sql=3, deser=3, config_changes=["x"] * 4))
        # 75 + 90 + 20 = 185 → 100
        assert score == 100


class TestContributingFactors:
    def test_non_secrets_returns_three_factors(self, scorer):
        _, factors, _ = scorer.score(_metrics())
        assert len(factors) == 3

    def test_factor_dimension_is_security(self, scorer):
        _, factors, _ = scorer.score(_metrics())
        assert all(f.dimension == "security" for f in factors)

    def test_factor_metric_names_without_secrets(self, scorer):
        _, factors, _ = scorer.score(_metrics())
        names = {f.metric_name for f in factors}
        assert names == {"sql_patterns_detected", "unsafe_deserialization_detected", "security_config_changes"}
