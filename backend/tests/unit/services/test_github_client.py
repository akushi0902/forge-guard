"""Unit tests for GitHubApiClient and utility functions (WO-091).

Covers:
  - post_status_check: success, 401 error, 403 rate limit, 404 not found
  - post_pr_comment: success, error handling
  - risk_score_to_github_state: all threshold boundaries
  - build_pr_comment: formatting, top-5 findings, severity ordering
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from forgeguard.services.github_client import (
    GitHubApiClient,
    GitHubClientError,
    build_pr_comment,
    risk_score_to_github_state,
)
from tests.fixtures.github_api_responses import (
    not_found_response,
    pr_comment_created,
    rate_limit_exceeded,
    rate_limit_exceeded_headers,
    status_check_created,
    unauthorized_response,
)


def _make_response(status_code: int, body: dict, headers: dict | None = None) -> httpx.Response:
    """Build a mock httpx.Response."""
    return httpx.Response(
        status_code=status_code,
        headers=headers or {},
        content=json.dumps(body).encode(),
    )


class TestRiskScoreToGithubState:
    def test_score_0_is_success(self):
        state, desc = risk_score_to_github_state(0)
        assert state == "success"
        assert "Low risk" in desc

    def test_score_30_is_success(self):
        state, desc = risk_score_to_github_state(30)
        assert state == "success"
        assert "Low risk" in desc

    def test_score_31_is_success_moderate(self):
        state, desc = risk_score_to_github_state(31)
        assert state == "success"
        assert "Moderate risk" in desc

    def test_score_60_is_success_moderate(self):
        state, desc = risk_score_to_github_state(60)
        assert state == "success"
        assert "Moderate risk" in desc

    def test_score_61_is_failure(self):
        state, desc = risk_score_to_github_state(61)
        assert state == "failure"
        assert "High risk" in desc

    def test_score_100_is_failure(self):
        state, desc = risk_score_to_github_state(100)
        assert state == "failure"

    def test_description_includes_score_integer(self):
        _, desc = risk_score_to_github_state(45.6)
        assert "46" in desc

    def test_description_max_140_chars(self):
        _, desc = risk_score_to_github_state(75)
        assert len(desc) <= 140


class TestBuildPrComment:
    def test_includes_risk_score(self):
        comment = build_pr_comment(
            assessment_id="test-uuid",
            risk_score=25.0,
            findings=[],
            target_url="https://forgeguard.example.com/assessments/test-uuid",
        )
        assert "25" in comment
        assert "ForgeGuard" in comment

    def test_includes_link(self):
        url = "https://forgeguard.example.com/api/v1/releases/test-uuid"
        comment = build_pr_comment(
            assessment_id="test-uuid",
            risk_score=25.0,
            findings=[],
            target_url=url,
        )
        assert url in comment

    def test_includes_assessment_id(self):
        comment = build_pr_comment(
            assessment_id="test-uuid-123",
            risk_score=25.0,
            findings=[],
            target_url="https://example.com",
        )
        assert "test-uuid-123" in comment

    def test_top_5_findings_ordered_by_severity(self):
        findings = [
            {"severity": "low", "title": "Low finding", "dimension": "docs"},
            {"severity": "critical", "title": "Critical finding", "dimension": "security"},
            {"severity": "high", "title": "High finding", "dimension": "code_quality"},
            {"severity": "medium", "title": "Medium finding 1"},
            {"severity": "medium", "title": "Medium finding 2"},
            {"severity": "low", "title": "Low finding 2"},  # 6th — should be excluded
        ]
        comment = build_pr_comment(
            assessment_id="abc",
            risk_score=75.0,
            findings=findings,
            target_url="https://example.com",
        )
        # Critical should appear before Low in the comment
        critical_pos = comment.find("Critical finding")
        low_pos = comment.find("Low finding 2")
        assert critical_pos < low_pos or low_pos == -1  # Low finding 2 excluded

    def test_no_findings_section_when_empty(self):
        comment = build_pr_comment(
            assessment_id="abc",
            risk_score=25.0,
            findings=[],
            target_url="https://example.com",
        )
        assert "Top Findings" not in comment

    def test_low_risk_badge(self):
        comment = build_pr_comment(
            assessment_id="abc", risk_score=20.0, findings=[], target_url="https://example.com"
        )
        assert "Low Risk" in comment

    def test_moderate_risk_badge(self):
        comment = build_pr_comment(
            assessment_id="abc", risk_score=45.0, findings=[], target_url="https://example.com"
        )
        assert "Moderate Risk" in comment

    def test_high_risk_badge(self):
        comment = build_pr_comment(
            assessment_id="abc", risk_score=80.0, findings=[], target_url="https://example.com"
        )
        assert "High Risk" in comment


class TestGitHubApiClientPostStatusCheck:
    @pytest.mark.asyncio
    async def test_success_201(self):
        client = GitHubApiClient(token="test-token")
        mock_response = _make_response(201, status_check_created())

        with patch.object(
            httpx.AsyncClient, "post", new=AsyncMock(return_value=mock_response)
        ):
            await client.post_status_check(
                owner="acme",
                repo="payments",
                sha="abc123",
                state="success",
                description="Low risk — score: 25/100",
                target_url="https://forgeguard.example.com/releases/uuid",
            )

    @pytest.mark.asyncio
    async def test_401_raises_error(self):
        client = GitHubApiClient(token="bad-token")
        mock_response = _make_response(401, unauthorized_response())

        with patch.object(
            httpx.AsyncClient, "post", new=AsyncMock(return_value=mock_response)
        ):
            with pytest.raises(GitHubClientError) as exc_info:
                await client.post_status_check(
                    owner="acme", repo="payments", sha="abc123",
                    state="success", description="ok", target_url="https://example.com",
                )
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_403_raises_error(self):
        client = GitHubApiClient(token="test-token")
        mock_response = _make_response(
            403, rate_limit_exceeded(), headers=rate_limit_exceeded_headers()
        )

        with patch.object(
            httpx.AsyncClient, "post", new=AsyncMock(return_value=mock_response)
        ):
            with pytest.raises(GitHubClientError) as exc_info:
                await client.post_status_check(
                    owner="acme", repo="payments", sha="abc123",
                    state="success", description="ok", target_url="https://example.com",
                )
            assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_404_raises_error(self):
        client = GitHubApiClient(token="test-token")
        mock_response = _make_response(404, not_found_response())

        with patch.object(
            httpx.AsyncClient, "post", new=AsyncMock(return_value=mock_response)
        ):
            with pytest.raises(GitHubClientError) as exc_info:
                await client.post_status_check(
                    owner="acme", repo="payments", sha="abc123",
                    state="success", description="ok", target_url="https://example.com",
                )
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_description_truncated_to_140_chars(self):
        client = GitHubApiClient(token="test-token")
        long_desc = "x" * 200
        mock_response = _make_response(201, status_check_created())
        captured_payload = {}

        async def mock_post(url, *, json=None, **kwargs):
            captured_payload.update(json or {})
            return mock_response

        with patch.object(httpx.AsyncClient, "post", new=AsyncMock(side_effect=mock_post)):
            await client.post_status_check(
                owner="acme", repo="payments", sha="abc123",
                state="success", description=long_desc, target_url="https://example.com",
            )
        assert len(captured_payload.get("description", "")) <= 140

    @pytest.mark.asyncio
    async def test_context_is_forgeguard_release_risk(self):
        client = GitHubApiClient(token="test-token")
        mock_response = _make_response(201, status_check_created())
        captured_payload = {}

        async def mock_post(url, *, json=None, **kwargs):
            captured_payload.update(json or {})
            return mock_response

        with patch.object(httpx.AsyncClient, "post", new=AsyncMock(side_effect=mock_post)):
            await client.post_status_check(
                owner="acme", repo="payments", sha="abc123",
                state="success", description="ok", target_url="https://example.com",
            )
        assert captured_payload.get("context") == "forgeguard/release-risk"


class TestGitHubApiClientPostPrComment:
    @pytest.mark.asyncio
    async def test_success_201(self):
        client = GitHubApiClient(token="test-token")
        mock_response = _make_response(201, pr_comment_created())

        with patch.object(
            httpx.AsyncClient, "post", new=AsyncMock(return_value=mock_response)
        ):
            await client.post_pr_comment(
                owner="acme",
                repo="payments",
                pr_number=42,
                body="## ForgeGuard Assessment",
            )

    @pytest.mark.asyncio
    async def test_401_raises_error(self):
        client = GitHubApiClient(token="bad-token")
        mock_response = _make_response(401, unauthorized_response())

        with patch.object(
            httpx.AsyncClient, "post", new=AsyncMock(return_value=mock_response)
        ):
            with pytest.raises(GitHubClientError) as exc_info:
                await client.post_pr_comment(
                    owner="acme", repo="payments", pr_number=42, body="test"
                )
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_token_not_in_error_message(self):
        secret_token = "my-super-secret-token-12345"
        client = GitHubApiClient(token=secret_token)
        mock_response = _make_response(401, unauthorized_response())

        with patch.object(
            httpx.AsyncClient, "post", new=AsyncMock(return_value=mock_response)
        ):
            with pytest.raises(GitHubClientError) as exc_info:
                await client.post_pr_comment(
                    owner="acme", repo="payments", pr_number=42, body="test"
                )
            # Token must not appear in the error message.
            assert secret_token not in str(exc_info.value)
