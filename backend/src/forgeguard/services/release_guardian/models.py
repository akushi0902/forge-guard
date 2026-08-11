"""Pydantic data models for the Release Guardian change analysis engine.

All models are used as structured data transfer objects — they are serialized
to JSONB and stored in the change_analysis column of release_assessments.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class CVEInfo(BaseModel):
    """A known CVE entry from the local CVE database."""

    id: str
    severity: str
    affected_package: str
    affected_versions: Optional[str] = None
    description: Optional[str] = None


class DependencyChange(BaseModel):
    """A single dependency that was added, removed, or updated."""

    name: str
    change_type: str  # added | removed | updated
    from_version: Optional[str] = None
    to_version: Optional[str] = None


class ComplexityMetrics(BaseModel):
    """Code complexity and churn metrics for the change."""

    files_changed: int = 0
    lines_added: int = 0
    lines_deleted: int = 0
    cyclomatic_complexity_delta: float = 0.0
    max_file_complexity: float = 0.0
    churn_score: float = Field(default=0.0, ge=0.0, le=1.0)


class CoverageMetrics(BaseModel):
    """Test coverage impact metrics for the change."""

    test_files_changed: int = 0
    test_lines_added: int = 0
    estimated_coverage_delta: float = 0.0
    has_new_tests: bool = False
    test_to_code_ratio: float = 0.0


class DependencyMetrics(BaseModel):
    """Dependency change and vulnerability metrics."""

    dependencies_added: list[str] = Field(default_factory=list)
    dependencies_removed: list[str] = Field(default_factory=list)
    dependencies_updated: list[DependencyChange] = Field(default_factory=list)
    known_cves: list[CVEInfo] = Field(default_factory=list)
    major_version_bumps: int = 0


class SecurityMetrics(BaseModel):
    """Security anti-pattern detection metrics."""

    secrets_detected: int = 0
    sql_patterns_detected: int = 0
    unsafe_deserialization_detected: int = 0
    security_config_changes: list[str] = Field(default_factory=list)


class AnalysisMetadata(BaseModel):
    """Metadata about the analysis run itself."""

    analysis_duration_ms: int = 0
    incomplete_dimensions: list[str] = Field(default_factory=list)
    provider: str = "unknown"


class ChangeAnalysisResult(BaseModel):
    """Complete structured output of the change analysis pipeline.

    Stored as JSONB in release_assessments.change_analysis.
    """

    complexity: ComplexityMetrics = Field(default_factory=ComplexityMetrics)
    coverage: CoverageMetrics = Field(default_factory=CoverageMetrics)
    dependencies: DependencyMetrics = Field(default_factory=DependencyMetrics)
    security: SecurityMetrics = Field(default_factory=SecurityMetrics)
    metadata: AnalysisMetadata = Field(default_factory=AnalysisMetadata)


# ---------------------------------------------------------------------------
# Provider data models (inputs to analyzers)
# ---------------------------------------------------------------------------


class FileChange(BaseModel):
    """A single file changed in a commit or PR."""

    filename: str
    status: str  # added | modified | removed | renamed
    additions: int = 0
    deletions: int = 0
    patch: Optional[str] = None
    is_binary: bool = False


class DiffResult(BaseModel):
    """Aggregated diff data for a commit."""

    commit_sha: Optional[str] = None
    total_additions: int = 0
    total_deletions: int = 0
    files: list[FileChange] = Field(default_factory=list)


class PRMetadata(BaseModel):
    """GitHub pull-request metadata."""

    pr_number: Optional[int] = None
    title: Optional[str] = None
    base_branch: Optional[str] = None
    head_branch: Optional[str] = None
    state: Optional[str] = None
    merge_commit_sha: Optional[str] = None


class DependencyManifest(BaseModel):
    """Parsed diff for a single dependency manifest file."""

    filename: str
    manifest_type: str  # requirements | pyproject | package_json
    added_dependencies: list[DependencyChange] = Field(default_factory=list)
    removed_dependencies: list[DependencyChange] = Field(default_factory=list)
    updated_dependencies: list[DependencyChange] = Field(default_factory=list)
    patch: Optional[str] = None


# ---------------------------------------------------------------------------
# Risk Scoring models (WO-046)
# ---------------------------------------------------------------------------

#: Default equal-weight configuration for risk scoring.
_DEFAULT_WEIGHTS: dict[str, float] = {
    "code_complexity": 0.25,
    "test_coverage": 0.25,
    "dependencies": 0.25,
    "security": 0.25,
}


class ContributingFactor(BaseModel):
    """A single metric that contributed to a dimension risk score.

    Used to explain WHY a score is high — stored in contributing_factors JSONB.
    """

    metric_name: str
    actual_value: float
    threshold: float
    risk_contribution: float
    dimension: str


class RiskScoreResult(BaseModel):
    """Complete output of the RiskScorer for a single ChangeAnalysisResult.

    Stored via AssessmentScoreRepository with score_type='risk'.
    overall_score is integer 0-100 (lower is safer).
    """

    overall_score: int = Field(ge=0, le=100)
    dimension_scores: dict[str, int]
    contributing_factors: list[ContributingFactor] = Field(default_factory=list)
    weights_used: dict[str, float]
    scored_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )


class RiskScoringConfig(BaseModel):
    """Configuration for the RiskScorer algorithm.

    Weights must sum to exactly 1.0 (validated at model creation).
    critical_security_floor is the minimum overall_score enforced when the
    security dimension detects secrets.
    """

    dimension_weights: dict[str, float] = Field(
        default_factory=lambda: dict(_DEFAULT_WEIGHTS)
    )
    critical_security_floor: int = Field(default=70, ge=0, le=100)

    @field_validator("dimension_weights")
    @classmethod
    def weights_must_sum_to_one(cls, v: dict[str, float]) -> dict[str, float]:
        total = sum(Decimal(str(w)) for w in v.values())
        if abs(total - Decimal("1.0")) > Decimal("0.0001"):
            raise ValueError(
                f"dimension_weights must sum to 1.0, got {float(total):.6f}"
            )
        return v


# ---------------------------------------------------------------------------
# Risk Finding models (WO-047)
# ---------------------------------------------------------------------------


class RiskSeverity(str, Enum):
    """Severity level for a risk finding."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RiskDimension(str, Enum):
    """Analysis dimension for a risk finding."""

    CODE_COMPLEXITY = "code_complexity"
    TEST_COVERAGE = "test_coverage"
    DEPENDENCIES = "dependencies"
    SECURITY = "security"
    HISTORICAL = "historical"


class FindingSource(str, Enum):
    """Indicates whether a finding's explanation was AI-generated or template-based."""

    AI_GENERATED = "ai-generated"
    TEMPLATE_GENERATED = "template-generated"


class RiskFinding(BaseModel):
    """A single risk finding produced by the ExplanationGenerator.

    Contains natural-language explanation, business impact, and remediation
    guidance for a specific risk detected in a release change analysis.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    assessment_id: str
    service_id: str
    title: str
    severity: RiskSeverity
    dimension: RiskDimension
    explanation: str
    business_impact: str
    remediation_steps: list[str]
    evidence: dict = Field(default_factory=dict)
    confidence_score: float = Field(ge=0.0, le=1.0)
    source: FindingSource
