"""Abstract ChangeDataProvider interface for the Release Guardian.

All concrete adapters (GitHubAdapter, MockChangeDataProvider) implement this
interface.  Business logic depends only on this ABC — never on a concrete class.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from .models import DependencyManifest, DiffResult, FileChange, PRMetadata


class ChangeDataProviderError(Exception):
    """Wraps all provider errors with structured context.

    GitHub API token is never included — only endpoint, status code,
    and the commit SHA that triggered the failure.
    """

    def __init__(
        self,
        message: str,
        *,
        endpoint: Optional[str] = None,
        status_code: Optional[int] = None,
        commit_sha: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.endpoint = endpoint
        self.status_code = status_code
        self.commit_sha = commit_sha


class ChangeAnalysisTimeoutError(Exception):
    """Raised when the 30-second overall analysis timeout is exceeded."""

    def __init__(self, message: str, *, partial_result: object = None) -> None:
        super().__init__(message)
        self.partial_result = partial_result


class DimensionAnalysisError(Exception):
    """Wraps a single dimension analyzer failure."""

    def __init__(self, message: str, *, dimension: str) -> None:
        super().__init__(message)
        self.dimension = dimension


class ChangeDataProvider(ABC):
    """Abstract interface for fetching raw change data from a repository."""

    @abstractmethod
    async def get_commit_diff(self, commit_sha: str) -> DiffResult:
        """Fetch the full diff for a commit SHA."""

    @abstractmethod
    async def get_pr_metadata(self, pr_reference: str) -> PRMetadata:
        """Fetch metadata for a pull request reference (URL or number)."""

    @abstractmethod
    async def get_file_changes(self, commit_sha: str) -> list[FileChange]:
        """Return the list of file changes for a commit."""

    @abstractmethod
    async def get_dependency_manifests(
        self, commit_sha: str, file_paths: list[str]
    ) -> list[DependencyManifest]:
        """Return parsed dependency manifest diffs for the given file paths."""
