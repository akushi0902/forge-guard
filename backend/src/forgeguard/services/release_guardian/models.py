"""Pydantic data models for the Release Guardian change analysis engine.

All models are used as structured data transfer objects — they are serialized
to JSONB and stored in the change_analysis column of release_assessments.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


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
