"""GitHub API client for posting commit status checks and PR comments.

Security requirements:
  - GITHUB_API_TOKEN is never logged, included in error responses, or stored
    anywhere beyond this module.
  - All error messages reference only the endpoint path and HTTP status code.

Usage::

    client = GitHubApiClient(token=settings.github_api_token)
    await client.post_status_check(
        owner="acme", repo="payments",
        sha="abc123", state="pending",
        description="ForgeGuard assessment running",
        target_url="https://forgeguard.example.com/releases/123",
    )
    await client.post_pr_comment(
        owner="acme", repo="payments",
        pr_number=42, body="## ForgeGuard Assessment\\n\\nRisk score: 25/100",
    )
"""

from __future__ import annotations

from typing import Optional

import httpx
import structlog

logger = structlog.get_logger(__name__)

_DEFAULT_BASE_URL = "https://api.github.com"
_DEFAULT_TIMEOUT = 15.0
_CONTEXT = "forgeguard/release-risk"


class GitHubClientError(Exception):
    """Raised when a GitHub API call fails after retries."""

    def __init__(self, message: str, *, endpoint: str, status_code: int) -> None:
        super().__init__(message)
        self.endpoint = endpoint
        self.status_code = status_code


class GitHubApiClient:
    """Async GitHub REST API client for ForgeGuard webhook callbacks.

    Posts commit status checks and PR comments back to GitHub after an
    assessment completes.

    Args:
        token:    GitHub API token (Personal Access Token or App token).
                  Must NEVER be logged or included in error messages.
        base_url: GitHub API base URL (override for GitHub Enterprise).
        timeout:  HTTP request timeout in seconds.
    """

    def __init__(
        self,
        token: str,
        *,
        base_url: str = _DEFAULT_BASE_URL,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        self._token = token
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def post_status_check(
        self,
        *,
        owner: str,
        repo: str,
        sha: str,
        state: str,
        description: str,
        target_url: str,
    ) -> None:
        """POST a commit status check to GitHub.

        Args:
            owner:       Repository owner (user or org name).
            repo:        Repository name.
            sha:         Commit SHA to attach the status to.
            state:       One of 'pending', 'success', 'failure', 'error'.
            description: Short human-readable description (max 140 chars).
            target_url:  Link to the ForgeGuard assessment detail page.
        """
        endpoint = f"/repos/{owner}/{repo}/statuses/{sha}"
        payload = {
            "state": state,
            "description": description[:140],
            "target_url": target_url,
            "context": _CONTEXT,
        }
        async with self._make_client() as client:
            response = await client.post(endpoint, json=payload)
        self._raise_for_status(response, endpoint)
        logger.info(
            "github_client.status_posted",
            owner=owner,
            repo=repo,
            sha=sha[:8],
            state=state,
        )

    async def post_pr_comment(
        self,
        *,
        owner: str,
        repo: str,
        pr_number: int,
        body: str,
    ) -> None:
        """POST a comment to a GitHub Pull Request.

        Args:
            owner:     Repository owner.
            repo:      Repository name.
            pr_number: Pull request number.
            body:      Markdown comment body.
        """
        endpoint = f"/repos/{owner}/{repo}/issues/{pr_number}/comments"
        async with self._make_client() as client:
            response = await client.post(endpoint, json={"body": body})
        self._raise_for_status(response, endpoint)
        logger.info(
            "github_client.comment_posted",
            owner=owner,
            repo=repo,
            pr_number=pr_number,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _make_client(self) -> httpx.AsyncClient:
        headers: dict[str, str] = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return httpx.AsyncClient(
            base_url=self._base_url,
            headers=headers,
            timeout=self._timeout,
        )

    def _raise_for_status(self, response: httpx.Response, endpoint: str) -> None:
        if response.is_success:
            return
        status = response.status_code
        if status == 401:
            logger.error("github_client.auth_error", endpoint=endpoint)
            raise GitHubClientError(
                "GitHub API token is invalid or expired",
                endpoint=endpoint,
                status_code=status,
            )
        if status == 403:
            remaining = response.headers.get("X-RateLimit-Remaining", "-1")
            if remaining == "0":
                logger.warning("github_client.rate_limit", endpoint=endpoint)
            raise GitHubClientError(
                "GitHub API access forbidden",
                endpoint=endpoint,
                status_code=status,
            )
        if status == 404:
            raise GitHubClientError(
                f"GitHub resource not found: {endpoint}",
                endpoint=endpoint,
                status_code=status,
            )
        if status == 422:
            raise GitHubClientError(
                f"GitHub rejected payload for {endpoint}",
                endpoint=endpoint,
                status_code=status,
            )
        raise GitHubClientError(
            f"GitHub API error {status}",
            endpoint=endpoint,
            status_code=status,
        )


def risk_score_to_github_state(score: float) -> tuple[str, str]:
    """Map a ForgeGuard risk score to a GitHub commit status state and description.

    Risk score thresholds:
      score <= 30  → 'success'  ('Low risk — score: N/100')
      score <= 60  → 'success'  ('Moderate risk — score: N/100')
      score >  60  → 'failure'  ('High risk — score: N/100')

    Returns:
        (state, description) tuple.
    """
    score_int = round(score)
    if score <= 30:
        return "success", f"Low risk — score: {score_int}/100"
    if score <= 60:
        return "success", f"Moderate risk — score: {score_int}/100 (review recommended)"
    return "failure", f"High risk — score: {score_int}/100 (action required)"


def build_pr_comment(
    *,
    assessment_id: str,
    risk_score: float,
    findings: list[dict],
    target_url: str,
) -> str:
    """Build a markdown PR comment summarising the ForgeGuard assessment.

    Args:
        assessment_id: UUID of the release assessment.
        risk_score:    Overall risk score (0–100).
        findings:      List of finding dicts (severity, title, dimension).
        target_url:    Link to the ForgeGuard assessment detail page.

    Returns:
        Markdown string for posting as a PR comment.
    """
    score_int = round(risk_score)
    if score_int <= 30:
        badge = "🟢 Low Risk"
    elif score_int <= 60:
        badge = "🟡 Moderate Risk"
    else:
        badge = "🔴 High Risk"

    lines: list[str] = [
        "## ForgeGuard Release Assessment",
        "",
        f"**Risk Score:** {score_int}/100 — {badge}",
        "",
    ]

    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    top_findings = sorted(
        findings,
        key=lambda f: (severity_order.get(f.get("severity", "low"), 4), f.get("title", "")),
    )[:5]

    if top_findings:
        lines.append("### Top Findings")
        lines.append("")
        for f in top_findings:
            sev = f.get("severity", "unknown").upper()
            title = f.get("title", "(untitled)")
            dim = f.get("dimension", "")
            lines.append(f"- **[{sev}]** {title}" + (f" _(_{dim}_)_" if dim else ""))
        lines.append("")

    lines += [
        f"[View full assessment in ForgeGuard]({target_url})",
        "",
        f"_Assessment ID: `{assessment_id}`_",
    ]

    return "\n".join(lines)
