"""ChangeAnalyzer — orchestrator for the release change analysis pipeline.

Coordinates the four dimension analyzers in parallel using asyncio.gather,
enforces an overall 30-second timeout, and assembles the final
ChangeAnalysisResult.  Partial results are returned when a dimension fails or
the timeout is exceeded — the incomplete_dimensions flag in metadata records
which dimensions did not complete.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Optional

import structlog

from .analyzers.complexity_analyzer import ComplexityAnalyzer
from .analyzers.coverage_analyzer import CoverageAnalyzer
from .analyzers.dependency_analyzer import DependencyAnalyzer
from .analyzers.security_analyzer import SecurityAnalyzer
from .models import (
    AnalysisMetadata,
    ChangeAnalysisResult,
    ComplexityMetrics,
    CoverageMetrics,
    DependencyMetrics,
    SecurityMetrics,
)
from .providers import (
    ChangeAnalysisTimeoutError,
    ChangeDataProvider,
    DimensionAnalysisError,
)

logger = structlog.get_logger(__name__)

_DEFAULT_TIMEOUT_SECONDS = 30.0


class ChangeAnalyzer:
    """Orchestrates all four dimension analyzers for a commit or PR.

    Args:
        provider:          Data source (GitHubAdapter or MockChangeDataProvider).
        timeout_seconds:   Hard timeout for the full analysis.
    """

    def __init__(
        self,
        provider: ChangeDataProvider,
        *,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._provider = provider
        self._timeout = timeout_seconds
        self._complexity = ComplexityAnalyzer()
        self._coverage = CoverageAnalyzer()
        self._dependency = DependencyAnalyzer()
        self._security = SecurityAnalyzer()

    async def analyze(
        self,
        service_id: uuid.UUID,
        *,
        commit_sha: Optional[str] = None,
        pr_reference: Optional[str] = None,
    ) -> ChangeAnalysisResult:
        """Run the full analysis pipeline and return a ChangeAnalysisResult.

        Args:
            service_id:   UUID of the service being assessed (for logging).
            commit_sha:   40-character hex SHA of the commit.  Required unless
                          pr_reference is provided.
            pr_reference: GitHub PR URL or number.  When provided, the PR's
                          merge commit SHA is resolved and used for analysis.

        Raises:
            ChangeAnalysisTimeoutError: Timeout exceeded; partial results
                included on the exception.
            ValueError: Neither commit_sha nor pr_reference was provided.
        """
        if not commit_sha and not pr_reference:
            raise ValueError("Either commit_sha or pr_reference must be provided")

        log = logger.bind(
            service_id=str(service_id),
            commit_sha=commit_sha,
            pr_reference=pr_reference,
        )
        log.info("change_analyzer.starting")
        start_ms = int(time.monotonic() * 1000)

        # Resolve commit SHA from PR reference if needed
        sha = commit_sha
        if not sha and pr_reference:
            pr_meta = await self._provider.get_pr_metadata(pr_reference)
            sha = pr_meta.merge_commit_sha or pr_reference

        # Fetch diff and file list in parallel
        try:
            diff, file_changes = await asyncio.wait_for(
                asyncio.gather(
                    self._provider.get_commit_diff(sha or ""),
                    self._provider.get_file_changes(sha or ""),
                ),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError as exc:
            elapsed = int(time.monotonic() * 1000) - start_ms
            partial = ChangeAnalysisResult(
                metadata=AnalysisMetadata(
                    analysis_duration_ms=elapsed,
                    incomplete_dimensions=["complexity", "coverage", "dependency", "security"],
                    provider=type(self._provider).__name__,
                )
            )
            log.error("change_analyzer.data_fetch_timeout", duration_ms=elapsed)
            raise ChangeAnalysisTimeoutError(
                "Data fetch timed out", partial_result=partial
            ) from exc

        # Identify dependency manifest files
        dep_filenames = [
            f.filename for f in file_changes
            if any(
                kw in f.filename.lower()
                for kw in ("requirements", "pyproject.toml", "package.json", "pipfile")
            )
        ]

        # Fetch dependency manifests
        manifests = await self._provider.get_dependency_manifests(sha or "", dep_filenames)

        # Run dimension analyzers in parallel within the remaining budget
        elapsed_so_far = (int(time.monotonic() * 1000) - start_ms) / 1000.0
        remaining = max(self._timeout - elapsed_so_far, 1.0)

        complexity_result: ComplexityMetrics = ComplexityMetrics()
        coverage_result: CoverageMetrics = CoverageMetrics()
        dependency_result: DependencyMetrics = DependencyMetrics()
        security_result: SecurityMetrics = SecurityMetrics()
        incomplete: list[str] = []

        try:
            results = await asyncio.wait_for(
                asyncio.gather(
                    self._run_dimension("complexity", self._complexity.analyze, file_changes),
                    self._run_dimension("coverage", self._coverage.analyze, file_changes),
                    self._run_dimension("dependency", self._dependency.analyze, manifests),
                    self._run_dimension("security", self._security.analyze, file_changes),
                    return_exceptions=True,
                ),
                timeout=remaining,
            )
            c, cv, d, s = results
            if isinstance(c, ComplexityMetrics):
                complexity_result = c
            else:
                incomplete.append("complexity")
                log.warning("change_analyzer.dimension_failed", dimension="complexity", error=str(c))

            if isinstance(cv, CoverageMetrics):
                coverage_result = cv
            else:
                incomplete.append("coverage")
                log.warning("change_analyzer.dimension_failed", dimension="coverage", error=str(cv))

            if isinstance(d, DependencyMetrics):
                dependency_result = d
            else:
                incomplete.append("dependency")
                log.warning("change_analyzer.dimension_failed", dimension="dependency", error=str(d))

            if isinstance(s, SecurityMetrics):
                security_result = s
            else:
                incomplete.append("security")
                log.warning("change_analyzer.dimension_failed", dimension="security", error=str(s))

        except asyncio.TimeoutError:
            elapsed = int(time.monotonic() * 1000) - start_ms
            incomplete = [d for d in ["complexity", "coverage", "dependency", "security"]
                          if d not in incomplete]
            partial = ChangeAnalysisResult(
                complexity=complexity_result,
                coverage=coverage_result,
                dependencies=dependency_result,
                security=security_result,
                metadata=AnalysisMetadata(
                    analysis_duration_ms=elapsed,
                    incomplete_dimensions=incomplete,
                    provider=type(self._provider).__name__,
                ),
            )
            log.error("change_analyzer.dimension_timeout", duration_ms=elapsed)
            raise ChangeAnalysisTimeoutError(
                "Dimension analysis timed out", partial_result=partial
            )

        elapsed_ms = int(time.monotonic() * 1000) - start_ms
        result = ChangeAnalysisResult(
            complexity=complexity_result,
            coverage=coverage_result,
            dependencies=dependency_result,
            security=security_result,
            metadata=AnalysisMetadata(
                analysis_duration_ms=elapsed_ms,
                incomplete_dimensions=incomplete,
                provider=type(self._provider).__name__,
            ),
        )
        log.info("change_analyzer.complete", duration_ms=elapsed_ms, incomplete=incomplete)
        return result

    @staticmethod
    async def _run_dimension(name: str, fn, *args):
        """Wrap a synchronous analyzer call in a coroutine for asyncio.gather."""
        try:
            return fn(*args)
        except Exception as exc:
            raise DimensionAnalysisError(str(exc), dimension=name) from exc
