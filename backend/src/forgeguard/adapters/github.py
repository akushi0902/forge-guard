"""GitHub API adapter implementing ChangeDataProvider.

Security requirements:
  - GITHUB_TOKEN is NEVER logged, included in error responses, or stored
    in application state beyond this module.  It is injected exclusively
    via the GITHUB_TOKEN environment variable or the constructor argument.
  - API errors (401, 403, 404, 429) are wrapped in ChangeDataProviderError
    with only the endpoint and status code — no token data.
"""

from __future__ import annotations

import os
import re
from typing import Optional

import httpx
import structlog

from forgeguard.services.release_guardian.models import (
    DependencyChange,
    DependencyManifest,
    DiffResult,
    FileChange,
    PRMetadata,
)
from forgeguard.services.release_guardian.providers import (
    ChangeDataProvider,
    ChangeDataProviderError,
)

logger = structlog.get_logger(__name__)

_GITHUB_TOKEN_ENV = "GITHUB_TOKEN"
_DEFAULT_TIMEOUT = 15.0
_DEFAULT_BASE_URL = "https://api.github.com"

_DEP_FILENAMES = frozenset({"requirements.txt", "pyproject.toml", "package.json", "Pipfile"})

_PR_URL_PATTERN = re.compile(r"github\.com/([^/]+)/([^/]+)/pull/(\d+)")
_PR_NUM_PATTERN = re.compile(r"^#?(\d+)$")


class GitHubAdapter(ChangeDataProvider):
    """Fetches change data from the GitHub REST API.

    Args:
        owner:        Repository owner (user or organisation name).
        repo:         Repository name.
        base_url:     GitHub API base URL (override for GitHub Enterprise).
        token:        Personal access token or GitHub App token.  When omitted,
                      reads from the GITHUB_TOKEN environment variable.
        timeout:      HTTP request timeout in seconds.
    """

    PROVIDER_NAME = "github"

    def __init__(
        self,
        owner: str,
        repo: str,
        *,
        base_url: str = _DEFAULT_BASE_URL,
        token: Optional[str] = None,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        self._owner = owner
        self._repo = repo
        self._base_url = base_url.rstrip("/")
        self._token = token or os.environ.get(_GITHUB_TOKEN_ENV, "")
        self._timeout = timeout

    # ------------------------------------------------------------------
    # ChangeDataProvider implementation
    # ------------------------------------------------------------------

    async def get_commit_diff(self, commit_sha: str) -> DiffResult:
        endpoint = f"/repos/{self._owner}/{self._repo}/commits/{commit_sha}"
        async with self._make_client(accept="application/vnd.github+json") as client:
            response = await client.get(endpoint)
        self._raise_for_status(response, endpoint, commit_sha=commit_sha)
        data = response.json()
        files = [self._parse_file(f) for f in data.get("files", [])]
        return DiffResult(
            commit_sha=commit_sha,
            total_additions=data.get("stats", {}).get("additions", 0),
            total_deletions=data.get("stats", {}).get("deletions", 0),
            files=files,
        )

    async def get_pr_metadata(self, pr_reference: str) -> PRMetadata:
        pr_number = self._resolve_pr_number(pr_reference)
        endpoint = f"/repos/{self._owner}/{self._repo}/pulls/{pr_number}"
        async with self._make_client() as client:
            response = await client.get(endpoint)
        self._raise_for_status(response, endpoint)
        data = response.json()
        return PRMetadata(
            pr_number=data.get("number"),
            title=data.get("title"),
            base_branch=data.get("base", {}).get("ref"),
            head_branch=data.get("head", {}).get("ref"),
            state=data.get("state"),
            merge_commit_sha=data.get("merge_commit_sha"),
        )

    async def get_file_changes(self, commit_sha: str) -> list[FileChange]:
        endpoint = f"/repos/{self._owner}/{self._repo}/commits/{commit_sha}"
        async with self._make_client() as client:
            response = await client.get(endpoint)
        self._raise_for_status(response, endpoint, commit_sha=commit_sha)
        return [self._parse_file(f) for f in response.json().get("files", [])]

    async def get_dependency_manifests(
        self, commit_sha: str, file_paths: list[str]
    ) -> list[DependencyManifest]:
        manifests: list[DependencyManifest] = []
        dep_paths = [p for p in file_paths if any(p.endswith(dep) for dep in _DEP_FILENAMES)]
        if not dep_paths:
            return manifests

        # Fetch the commit diff to get patches for dep files
        endpoint = f"/repos/{self._owner}/{self._repo}/commits/{commit_sha}"
        async with self._make_client() as client:
            response = await client.get(endpoint)
        if response.status_code != 200:
            return manifests

        files_data = response.json().get("files", [])
        for file_raw in files_data:
            fname = file_raw.get("filename", "")
            if fname not in dep_paths:
                continue
            manifest_type = self._detect_manifest_type(fname)
            manifests.append(DependencyManifest(
                filename=fname,
                manifest_type=manifest_type,
                patch=file_raw.get("patch"),
            ))
        return manifests

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _make_client(self, *, accept: str = "application/vnd.github+json") -> httpx.AsyncClient:
        headers: dict[str, str] = {
            "Accept": accept,
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return httpx.AsyncClient(
            base_url=self._base_url,
            headers=headers,
            timeout=self._timeout,
        )

    def _raise_for_status(
        self,
        response: httpx.Response,
        endpoint: str,
        commit_sha: Optional[str] = None,
    ) -> None:
        if response.is_success:
            return
        status = response.status_code
        if status == 401:
            logger.error("github_adapter.auth_error", endpoint=endpoint)
            raise ChangeDataProviderError(
                "GitHub API token is invalid or expired",
                endpoint=endpoint, status_code=status, commit_sha=commit_sha,
            )
        if status == 403:
            remaining = response.headers.get("X-RateLimit-Remaining", "-1")
            if remaining == "0":
                logger.error("github_adapter.rate_limit", endpoint=endpoint)
                raise ChangeDataProviderError(
                    "GitHub API rate limit exceeded",
                    endpoint=endpoint, status_code=status, commit_sha=commit_sha,
                )
            logger.error("github_adapter.forbidden", endpoint=endpoint)
            raise ChangeDataProviderError(
                "GitHub API access forbidden",
                endpoint=endpoint, status_code=status, commit_sha=commit_sha,
            )
        if status == 404:
            raise ChangeDataProviderError(
                f"GitHub resource not found: {endpoint}",
                endpoint=endpoint, status_code=status, commit_sha=commit_sha,
            )
        if status == 429:
            retry_after = response.headers.get("Retry-After", "unknown")
            logger.error("github_adapter.rate_limit_429", retry_after=retry_after)
            raise ChangeDataProviderError(
                f"GitHub API rate limit (429); retry after {retry_after}s",
                endpoint=endpoint, status_code=status, commit_sha=commit_sha,
            )
        raise ChangeDataProviderError(
            f"GitHub API error {status}",
            endpoint=endpoint, status_code=status, commit_sha=commit_sha,
        )

    @staticmethod
    def _parse_file(raw: dict) -> FileChange:
        filename = raw.get("filename", "")
        # GitHub marks binary files by omitting the 'patch' field and setting
        # raw_url to a blob. Check for patch absence on non-trivial changes.
        patch = raw.get("patch")
        is_binary = patch is None and raw.get("additions", 0) + raw.get("deletions", 0) > 0
        return FileChange(
            filename=filename,
            status=raw.get("status", "modified"),
            additions=raw.get("additions", 0),
            deletions=raw.get("deletions", 0),
            patch=patch,
            is_binary=is_binary,
        )

    @staticmethod
    def _resolve_pr_number(pr_reference: str) -> str:
        """Extract a PR number from a URL or '#N' / 'N' string."""
        m = _PR_URL_PATTERN.search(pr_reference)
        if m:
            return m.group(3)
        m = _PR_NUM_PATTERN.match(pr_reference.strip())
        if m:
            return m.group(1)
        return pr_reference

    @staticmethod
    def _detect_manifest_type(filename: str) -> str:
        lower = filename.lower()
        if "requirements" in lower:
            return "requirements"
        if "pyproject" in lower:
            return "pyproject"
        if "package.json" in lower:
            return "package_json"
        if "pipfile" in lower:
            return "requirements"
        return "requirements"
