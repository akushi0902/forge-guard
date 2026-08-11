"""Unit tests for DependencyScorer — CVE severity, major bumps, new deps."""

from __future__ import annotations

import pytest

from forgeguard.services.release_guardian.models import CVEInfo, DependencyMetrics
from forgeguard.services.release_guardian.scorers.dependency_scorer import DependencyScorer


def _cve(severity: str, id: str = "CVE-2024-001", pkg: str = "libA"):
    return CVEInfo(id=id, severity=severity, affected_package=pkg)


def _metrics(deps_added=None, major_bumps=0, cves=None):
    return DependencyMetrics(
        dependencies_added=deps_added or [],
        major_version_bumps=major_bumps,
        known_cves=cves or [],
    )


@pytest.fixture
def scorer():
    return DependencyScorer()


class TestCVEScoring:
    def test_no_cves_zero_contribution(self, scorer):
        score, _ = scorer.score(_metrics())
        assert score == 0

    def test_single_critical_cve(self, scorer):
        score, _ = scorer.score(_metrics(cves=[_cve("critical")]))
        assert score == 30

    def test_single_high_cve(self, scorer):
        score, _ = scorer.score(_metrics(cves=[_cve("high")]))
        assert score == 20

    def test_single_medium_cve(self, scorer):
        score, _ = scorer.score(_metrics(cves=[_cve("medium")]))
        assert score == 10

    def test_single_low_cve(self, scorer):
        score, _ = scorer.score(_metrics(cves=[_cve("low")]))
        assert score == 5

    def test_multiple_cves_summed(self, scorer):
        cves = [_cve("critical", id="C1"), _cve("high", id="C2"), _cve("medium", id="C3")]
        score, _ = scorer.score(_metrics(cves=cves))
        # 30 + 20 + 10 = 60
        assert score == 60

    def test_cves_capped_at_100(self, scorer):
        # 4 critical = 120 → capped at 100
        cves = [_cve("critical", id=f"CVE-{i}", pkg=f"lib{i}") for i in range(4)]
        score, _ = scorer.score(_metrics(cves=cves))
        assert score == 100

    def test_unknown_severity_treated_as_zero(self, scorer):
        score, _ = scorer.score(_metrics(cves=[_cve("info")]))
        assert score == 0


class TestMajorVersionBumps:
    def test_zero_major_bumps(self, scorer):
        score, _ = scorer.score(_metrics(major_bumps=0))
        assert score == 0

    def test_one_major_bump_adds_10(self, scorer):
        score, _ = scorer.score(_metrics(major_bumps=1))
        assert score == 10

    def test_three_major_bumps_adds_30(self, scorer):
        score, _ = scorer.score(_metrics(major_bumps=3))
        assert score == 30

    def test_major_bumps_capped_at_30(self, scorer):
        score, _ = scorer.score(_metrics(major_bumps=10))
        assert score == 30


class TestNewDependencies:
    def test_five_or_fewer_no_contribution(self, scorer):
        score, _ = scorer.score(_metrics(deps_added=["a", "b", "c", "d", "e"]))
        assert score == 0

    def test_six_deps_adds_10(self, scorer):
        score, _ = scorer.score(_metrics(deps_added=[f"dep{i}" for i in range(6)]))
        assert score == 10

    def test_ten_deps_adds_10(self, scorer):
        score, _ = scorer.score(_metrics(deps_added=[f"dep{i}" for i in range(10)]))
        assert score == 10

    def test_eleven_deps_adds_20(self, scorer):
        score, _ = scorer.score(_metrics(deps_added=[f"dep{i}" for i in range(11)]))
        assert score == 20


class TestScoreCap:
    def test_all_components_capped_at_100(self, scorer):
        cves = [_cve("critical", id=f"CVE-{i}", pkg=f"lib{i}") for i in range(5)]
        score, _ = scorer.score(_metrics(deps_added=[f"d{i}" for i in range(12)], major_bumps=4, cves=cves))
        # 100 (CVEs) + 30 (major, capped) + 20 (deps) = 150 → 100
        assert score == 100


class TestContributingFactors:
    def test_returns_three_factors(self, scorer):
        _, factors = scorer.score(_metrics())
        assert len(factors) == 3

    def test_factor_dimension_is_dependencies(self, scorer):
        _, factors = scorer.score(_metrics())
        assert all(f.dimension == "dependencies" for f in factors)

    def test_factor_metric_names(self, scorer):
        _, factors = scorer.score(_metrics())
        names = {f.metric_name for f in factors}
        assert names == {"known_cves", "major_version_bumps", "dependencies_added"}
