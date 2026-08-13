"""Ten ChangeAnalysisResult fixtures with manually calculated expected risk scores.

Score formula (equal weights 0.25 each):
  overall = round(complexity*0.25 + coverage*0.25 + dependency*0.25 + security*0.25)
  if is_critical: overall = max(overall, 70)

Scores are computed using the documented threshold tables in each scorer module.
Any algorithm change that alters these expected values is a BREAKING CHANGE and
must be reviewed before merging.

Naming convention: SCENARIO_<N>_<short_description>
"""

from __future__ import annotations

from forgeguard.services.release_guardian.models import (
    AnalysisMetadata,
    ChangeAnalysisResult,
    ComplexityMetrics,
    CoverageMetrics,
    CVEInfo,
    DependencyMetrics,
    SecurityMetrics,
)

# ---------------------------------------------------------------------------
# Helper: build a ChangeAnalysisResult with zero defaults everywhere.
# ---------------------------------------------------------------------------

def _result(
    complexity: ComplexityMetrics | None = None,
    coverage: CoverageMetrics | None = None,
    dependencies: DependencyMetrics | None = None,
    security: SecurityMetrics | None = None,
    incomplete: list[str] | None = None,
) -> ChangeAnalysisResult:
    return ChangeAnalysisResult(
        complexity=complexity or ComplexityMetrics(),
        coverage=coverage or CoverageMetrics(),
        dependencies=dependencies or DependencyMetrics(),
        security=security or SecurityMetrics(),
        metadata=AnalysisMetadata(incomplete_dimensions=incomplete or []),
    )


# ---------------------------------------------------------------------------
# Fixture 1: Empty change — all metrics at zero.
#
# complexity_score: 0, coverage_score: 0, dependency_score: 0, security_score: 0
# overall = round(0*0.25 * 4) = 0
# ---------------------------------------------------------------------------
SCENARIO_1_EMPTY = _result()
EXPECTED_1 = 0

# ---------------------------------------------------------------------------
# Fixture 2: Small safe change — few files, positive coverage, no issues.
#
# complexity: files=3(<5→0), lines=40(<100→0), cc=2(<5→0), churn=0.1(<0.3→0) = 0
# coverage: delta=1.0(≥0→0), no_tests: has_new_tests=True→0, ratio=0.8(≥0.5→0) = 0
#           code_lines_added = 30 - 10 = 20 (but has_new_tests=True → no penalty)
# dependency: 0, security: 0
# overall = 0
# ---------------------------------------------------------------------------
SCENARIO_2_SMALL_SAFE = _result(
    complexity=ComplexityMetrics(
        files_changed=3, lines_added=30, lines_deleted=10,
        cyclomatic_complexity_delta=2.0, churn_score=0.1,
    ),
    coverage=CoverageMetrics(
        test_files_changed=2, test_lines_added=10,
        estimated_coverage_delta=1.0, has_new_tests=True, test_to_code_ratio=0.8,
    ),
)
EXPECTED_2 = 0

# ---------------------------------------------------------------------------
# Fixture 3: Medium change — code without tests, one SQL pattern.
#
# complexity: files=10(<20→15), lines=300(<500→15), cc=8(<15→10), churn=0.4(<0.7→15)
#             = 15+15+10+15 = 55
# coverage: delta=-2.0(≥-2.0→40), code_lines_added=250>10 no tests→30, ratio=0.0<0.1→45
#           total=115 → capped=100
# dependency: 0 CVEs, 0 major, 2 deps(≤5→0) = 0
# security: 1 SQL(25) = 25
# overall = round(55*0.25 + 100*0.25 + 0*0.25 + 25*0.25)
#         = round(13.75 + 25 + 0 + 6.25) = round(45) = 45
# ---------------------------------------------------------------------------
SCENARIO_3_MEDIUM_NO_TESTS = _result(
    complexity=ComplexityMetrics(
        files_changed=10, lines_added=250, lines_deleted=50,
        cyclomatic_complexity_delta=8.0, churn_score=0.4,
    ),
    coverage=CoverageMetrics(
        test_files_changed=0, test_lines_added=0,
        estimated_coverage_delta=-2.0, has_new_tests=False, test_to_code_ratio=0.0,
    ),
    dependencies=DependencyMetrics(
        dependencies_added=["libA", "libB"],
    ),
    security=SecurityMetrics(sql_patterns_detected=1),
)
EXPECTED_3 = 45

# ---------------------------------------------------------------------------
# Fixture 4: Small change with secrets detected (critical floor triggered).
#
# complexity: files=5(<20→15), lines=100(<500→15), cc=2(<5→0), churn=0.2(<0.3→0) = 30
# coverage: delta=0→0, code_lines_added=100>10 no tests→30, ratio=0.0<0.1→45, total=75
# dependency: 0
# security: secrets=1 → 100, is_critical=True
# without floor: round(30*0.25 + 75*0.25 + 0 + 100*0.25) = round(7.5+18.75+0+25) = round(51.25) = 51
# with floor: max(51, 70) = 70
# ---------------------------------------------------------------------------
SCENARIO_4_SECRETS_FLOOR = _result(
    complexity=ComplexityMetrics(
        files_changed=5, lines_added=100, lines_deleted=0,
        cyclomatic_complexity_delta=2.0, churn_score=0.2,
    ),
    coverage=CoverageMetrics(
        test_files_changed=0, test_lines_added=0,
        estimated_coverage_delta=0.0, has_new_tests=False, test_to_code_ratio=0.0,
    ),
    security=SecurityMetrics(secrets_detected=1),
)
EXPECTED_4 = 70

# ---------------------------------------------------------------------------
# Fixture 5: Dependency-heavy high risk.
#
# complexity: files=15(<20→15), lines=450(<500→15), cc=7(<15→10), churn=0.5(<0.7→15) = 55
# coverage: delta=-2.0→40, code_lines_added=400>10 no tests→30, ratio=0.05<0.1→45, total=115→100
# dependency: 2 critical CVEs=60, 1 high CVE=20, total cve=80(<100), 3 major*10=30, 8 deps>5→10
#             total=80+30+10=120→capped=100
# security: 0
# overall = round(55*0.25 + 100*0.25 + 100*0.25 + 0*0.25)
#         = round(13.75 + 25 + 25 + 0) = round(63.75) = 64
# ---------------------------------------------------------------------------
SCENARIO_5_DEPENDENCY_HEAVY = _result(
    complexity=ComplexityMetrics(
        files_changed=15, lines_added=400, lines_deleted=50,
        cyclomatic_complexity_delta=7.0, churn_score=0.5,
    ),
    coverage=CoverageMetrics(
        test_files_changed=0, test_lines_added=0,
        estimated_coverage_delta=-2.0, has_new_tests=False, test_to_code_ratio=0.05,
    ),
    dependencies=DependencyMetrics(
        dependencies_added=["a", "b", "c", "d", "e", "f", "g", "h"],
        major_version_bumps=3,
        known_cves=[
            CVEInfo(id="CVE-2024-001", severity="critical", affected_package="libA"),
            CVEInfo(id="CVE-2024-002", severity="critical", affected_package="libB"),
            CVEInfo(id="CVE-2024-003", severity="high",     affected_package="libC"),
        ],
    ),
)
EXPECTED_5 = 64

# ---------------------------------------------------------------------------
# Fixture 6: Coverage loss only — code added, no tests, no CVEs, no security.
#
# complexity: files=8(<20→15), lines=250(<500→15), cc=3(<5→0), churn=0.3(≥0.3→15) = 45
# coverage: delta=-2.0→40, code_lines_added=200>10 no tests→30, ratio=0.0<0.1→45, total=115→100
# dependency: 0
# security: 0
# overall = round(45*0.25 + 100*0.25 + 0 + 0) = round(11.25 + 25) = round(36.25) = 36
# ---------------------------------------------------------------------------
SCENARIO_6_COVERAGE_LOSS = _result(
    complexity=ComplexityMetrics(
        files_changed=8, lines_added=200, lines_deleted=50,
        cyclomatic_complexity_delta=3.0, churn_score=0.3,
    ),
    coverage=CoverageMetrics(
        test_files_changed=0, test_lines_added=0,
        estimated_coverage_delta=-2.0, has_new_tests=False, test_to_code_ratio=0.0,
    ),
)
EXPECTED_6 = 36

# ---------------------------------------------------------------------------
# Fixture 7: Test-only change — only test files added.
#
# complexity: files=5(<20→15), lines=100(<500→15), cc=2(<5→0), churn=0.0(<0.3→0) = 30
# coverage: code_lines_added = 100 - 100 = 0 → no penalties from ratio/no_tests
#           delta=2.0→0, no guard applied (code_lines=0), ratio=0(code=0)→0 = 0
# dependency: 0, security: 0
# overall = round(30*0.25 + 0 + 0 + 0) = round(7.5) = 8
# ---------------------------------------------------------------------------
SCENARIO_7_TEST_ONLY = _result(
    complexity=ComplexityMetrics(
        files_changed=5, lines_added=100, lines_deleted=0,
        cyclomatic_complexity_delta=2.0, churn_score=0.0,
    ),
    coverage=CoverageMetrics(
        test_files_changed=5, test_lines_added=100,
        estimated_coverage_delta=2.0, has_new_tests=True, test_to_code_ratio=1.0,
    ),
)
EXPECTED_7 = 8

# ---------------------------------------------------------------------------
# Fixture 8: Maximum risk — all dimensions saturated (no secrets).
#
# complexity: files=60(≥50→60), lines=1200(≥1000→55), cc=20(≥15→20), churn=0.9(≥0.7→25)
#             total=160→capped=100
# coverage: delta=-3.0(<-2.0→60), code=1200>10 no tests→30, ratio=0.0→45, total=135→100
# dependency: 5 critical CVEs=150→capped=100, 4 major*10=40→capped=30, 12 deps>10→20
#             total=150→capped=100
# security: 2 SQL=50, 3 deser=90, total=140→capped=100 (no secrets → not critical)
# overall = round(100*0.25 * 4) = 100
# ---------------------------------------------------------------------------
SCENARIO_8_MAX_RISK = _result(
    complexity=ComplexityMetrics(
        files_changed=60, lines_added=1200, lines_deleted=200,
        cyclomatic_complexity_delta=20.0, churn_score=0.9,
    ),
    coverage=CoverageMetrics(
        test_files_changed=0, test_lines_added=0,
        estimated_coverage_delta=-3.0, has_new_tests=False, test_to_code_ratio=0.0,
    ),
    dependencies=DependencyMetrics(
        dependencies_added=["a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k", "l"],
        major_version_bumps=4,
        known_cves=[
            CVEInfo(id="CVE-001", severity="critical", affected_package="x"),
            CVEInfo(id="CVE-002", severity="critical", affected_package="x"),
            CVEInfo(id="CVE-003", severity="critical", affected_package="x"),
            CVEInfo(id="CVE-004", severity="critical", affected_package="x"),
            CVEInfo(id="CVE-005", severity="critical", affected_package="x"),
        ],
    ),
    security=SecurityMetrics(
        sql_patterns_detected=2,
        unsafe_deserialization_detected=3,
    ),
)
EXPECTED_8 = 100

# ---------------------------------------------------------------------------
# Fixture 9: Secrets in minimal change — floor dominates.
#
# complexity: 0, coverage: 0 (has_new_tests=True), dependency: 0, security: secrets=1→100
# without floor: round(0 + 0 + 0 + 100*0.25) = round(25) = 25
# with floor: max(25, 70) = 70
# ---------------------------------------------------------------------------
SCENARIO_9_SECRETS_MINIMAL = _result(
    complexity=ComplexityMetrics(
        files_changed=2, lines_added=10, lines_deleted=0,
        cyclomatic_complexity_delta=0.0, churn_score=0.0,
    ),
    coverage=CoverageMetrics(
        test_files_changed=1, test_lines_added=5,
        estimated_coverage_delta=1.0, has_new_tests=True, test_to_code_ratio=1.0,
    ),
    security=SecurityMetrics(secrets_detected=1),
)
EXPECTED_9 = 70

# ---------------------------------------------------------------------------
# Fixture 10: Mixed medium risk — balanced across all dimensions.
#
# complexity: files=12(<20→15), lines=350(<500→15), cc=6(<15→10), churn=0.35(<0.7→15) = 55
# coverage: delta=-1.5(≥-2.0→40), code_lines_added=300>10 no tests→30, ratio=0.15(<0.2→30)
#           total=100→capped=100
# dependency: 1 medium CVE=10, 1 major=10, 4 deps(≤5→0), total=20
# security: 1 SQL=25
# overall = round(55*0.25 + 100*0.25 + 20*0.25 + 25*0.25)
#         = round(13.75 + 25 + 5 + 6.25) = round(50) = 50
# ---------------------------------------------------------------------------
SCENARIO_10_MIXED_MEDIUM = _result(
    complexity=ComplexityMetrics(
        files_changed=12, lines_added=300, lines_deleted=50,
        cyclomatic_complexity_delta=6.0, churn_score=0.35,
    ),
    coverage=CoverageMetrics(
        test_files_changed=0, test_lines_added=0,
        estimated_coverage_delta=-1.5, has_new_tests=False, test_to_code_ratio=0.15,
    ),
    dependencies=DependencyMetrics(
        dependencies_added=["a", "b", "c", "d"],
        major_version_bumps=1,
        known_cves=[
            CVEInfo(id="CVE-2024-100", severity="medium", affected_package="libX"),
        ],
    ),
    security=SecurityMetrics(sql_patterns_detected=1),
)
EXPECTED_10 = 50

# ---------------------------------------------------------------------------
# Collected list of (input, expected_score) tuples for parametrized tests.
# ---------------------------------------------------------------------------
RISK_SCORING_FIXTURES: list[tuple[ChangeAnalysisResult, int]] = [
    (SCENARIO_1_EMPTY, EXPECTED_1),
    (SCENARIO_2_SMALL_SAFE, EXPECTED_2),
    (SCENARIO_3_MEDIUM_NO_TESTS, EXPECTED_3),
    (SCENARIO_4_SECRETS_FLOOR, EXPECTED_4),
    (SCENARIO_5_DEPENDENCY_HEAVY, EXPECTED_5),
    (SCENARIO_6_COVERAGE_LOSS, EXPECTED_6),
    (SCENARIO_7_TEST_ONLY, EXPECTED_7),
    (SCENARIO_8_MAX_RISK, EXPECTED_8),
    (SCENARIO_9_SECRETS_MINIMAL, EXPECTED_9),
    (SCENARIO_10_MIXED_MEDIUM, EXPECTED_10),
]
