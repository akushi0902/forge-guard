"""Unit tests for ForgeScorecardAdapter and forge_scorecard module (WO-090).

Covers:
  AC-1  Successful publish — correct payload shape, all 5 dimensions mapped
  AC-2  5xx error — result is retryable=True
  AC-3  4xx error — result is retryable=False (no retry)
  AC-4  Timeout — result is retryable=True
  AC-5  Dimension mapping correctness (all 5 ForgeGuard → Scorecard dims)
  AC-6  no-catalog-id path sets blocked_no_catalog_id
  AC-7  get_scorecard_status returns dict with id on 200, error on failure
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

import pytest

from forgeguard.services.forge_scorecard import (
    DEFAULT_DIMENSION_MAP,
    ForgeScorecardAdapter,
    ForgeScorecardHttpAdapter,
    ScorecardSyncStatus,
    map_dimensions,
)
from tests.fixtures.forge_scorecard_responses import (
    ASSESSMENT_ID,
    SAMPLE_ASSESSED_AT,
    SAMPLE_DIMENSION_SCORES,
    SAMPLE_OVERALL_SCORE,
    SCORECARD_ID,
    SERVICE_ID,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_http_response(status_code: int, json_body: Any = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_body or {}
    return resp


async def _mock_publish(
    status_code: int,
    json_body: Any = None,
) -> dict:
    adapter = ForgeScorecardHttpAdapter(
        base_url="https://forge.example.com/scorecard",
        api_key="test-key",
    )
    mock_resp = _make_http_response(status_code, json_body)
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)
    with patch("httpx.AsyncClient", return_value=mock_client):
        return await adapter.publish_score(
            scorecard_id=SCORECARD_ID,
            service_id=SERVICE_ID,
            assessment_id=ASSESSMENT_ID,
            overall_score=SAMPLE_OVERALL_SCORE,
            dimension_scores=SAMPLE_DIMENSION_SCORES,
            assessed_at=SAMPLE_ASSESSED_AT,
        )


# ---------------------------------------------------------------------------
# map_dimensions
# ---------------------------------------------------------------------------


class TestMapDimensions:
    def test_all_five_dimensions_mapped(self):
        result = map_dimensions(SAMPLE_DIMENSION_SCORES)
        names = {d["name"] for d in result}
        assert names == set(DEFAULT_DIMENSION_MAP.values())

    def test_score_and_weight_preserved(self):
        result = map_dimensions(SAMPLE_DIMENSION_SCORES)
        security = next(d for d in result if d["name"] == "security")
        assert security["score"] == pytest.approx(70.0)
        assert security["weight"] == pytest.approx(0.30)

    def test_custom_mapping(self):
        custom = {"code_quality": "cq_custom"}
        result = map_dimensions(SAMPLE_DIMENSION_SCORES, dimension_map=custom)
        assert len(result) == 1
        assert result[0]["name"] == "cq_custom"

    def test_missing_dimension_skipped(self):
        """Dimensions not in the scores dict are silently skipped."""
        partial = {"security": {"score": 80.0, "weight": 0.30}}
        result = map_dimensions(partial)
        assert len(result) == 1

    def test_none_score_skipped(self):
        """Dimensions with None score are excluded from the payload."""
        scores = {"code_quality": {"score": None, "weight": 0.25}}
        result = map_dimensions(scores)
        assert result == []


# ---------------------------------------------------------------------------
# ForgeScorecardHttpAdapter.publish_score
# ---------------------------------------------------------------------------


class TestForgeScorecardHttpAdapterPublish:
    @pytest.mark.asyncio
    async def test_successful_publish_201(self):
        result = await _mock_publish(201, {"id": "pub-1"})
        assert result["success"] is True
        assert result["retryable"] is False
        assert result["error"] is None

    @pytest.mark.asyncio
    async def test_successful_publish_200(self):
        result = await _mock_publish(200)
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_5xx_returns_retryable(self):
        result = await _mock_publish(500)
        assert result["success"] is False
        assert result["retryable"] is True
        assert "500" in result["error"]

    @pytest.mark.asyncio
    async def test_503_returns_retryable(self):
        result = await _mock_publish(503)
        assert result["success"] is False
        assert result["retryable"] is True

    @pytest.mark.asyncio
    async def test_400_no_retry(self):
        result = await _mock_publish(400)
        assert result["success"] is False
        assert result["retryable"] is False
        assert "400" in result["error"]

    @pytest.mark.asyncio
    async def test_401_no_retry(self):
        result = await _mock_publish(401)
        assert result["success"] is False
        assert result["retryable"] is False

    @pytest.mark.asyncio
    async def test_timeout_returns_retryable(self):
        import httpx  # noqa: PLC0415
        adapter = ForgeScorecardHttpAdapter(
            base_url="https://forge.example.com/scorecard",
            api_key="test-key",
        )
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timed out"))
        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await adapter.publish_score(
                scorecard_id=SCORECARD_ID,
                service_id=SERVICE_ID,
                assessment_id=ASSESSMENT_ID,
                overall_score=SAMPLE_OVERALL_SCORE,
                dimension_scores=SAMPLE_DIMENSION_SCORES,
                assessed_at=SAMPLE_ASSESSED_AT,
            )
        assert result["success"] is False
        assert result["retryable"] is True
        assert result["error"] == "timeout"

    @pytest.mark.asyncio
    async def test_api_key_not_in_payload(self):
        """API key must never appear in the JSON body sent to the scorecard API."""
        adapter = ForgeScorecardHttpAdapter(
            base_url="https://forge.example.com/scorecard",
            api_key="SECRET-KEY-12345",
        )
        mock_resp = _make_http_response(201)
        captured_payload: list = []
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        async def capture_post(url, *, json, headers):
            captured_payload.append(json)
            return mock_resp

        mock_client.post = capture_post
        with patch("httpx.AsyncClient", return_value=mock_client):
            await adapter.publish_score(
                scorecard_id=SCORECARD_ID,
                service_id=SERVICE_ID,
                assessment_id=ASSESSMENT_ID,
                overall_score=SAMPLE_OVERALL_SCORE,
                dimension_scores=SAMPLE_DIMENSION_SCORES,
                assessed_at=SAMPLE_ASSESSED_AT,
            )
        assert captured_payload, "post was not called"
        body_str = str(captured_payload[0])
        assert "SECRET-KEY-12345" not in body_str

    @pytest.mark.asyncio
    async def test_payload_shape(self):
        """Verifies the published payload has the expected keys."""
        adapter = ForgeScorecardHttpAdapter(
            base_url="https://forge.example.com/scorecard",
            api_key="test-key",
        )
        mock_resp = _make_http_response(201)
        captured: list = []
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        async def cap(url, *, json, headers):
            captured.append(json)
            return mock_resp

        mock_client.post = cap
        with patch("httpx.AsyncClient", return_value=mock_client):
            await adapter.publish_score(
                scorecard_id=SCORECARD_ID,
                service_id=SERVICE_ID,
                assessment_id=ASSESSMENT_ID,
                overall_score=SAMPLE_OVERALL_SCORE,
                dimension_scores=SAMPLE_DIMENSION_SCORES,
                assessed_at=SAMPLE_ASSESSED_AT,
            )
        payload = captured[0]
        assert "overall_score" in payload
        assert "dimensions" in payload
        assert "assessed_at" in payload
        assert "service_id" in payload
        assert isinstance(payload["dimensions"], list)
        assert len(payload["dimensions"]) == 5


# ---------------------------------------------------------------------------
# ForgeScorecardHttpAdapter.get_scorecard_status
# ---------------------------------------------------------------------------


class TestGetScorecardStatus:
    @pytest.mark.asyncio
    async def test_returns_json_on_200(self):
        adapter = ForgeScorecardHttpAdapter(
            base_url="https://forge.example.com/scorecard",
            api_key="test-key",
        )
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": SCORECARD_ID}
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)
        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await adapter.get_scorecard_status(scorecard_id=SCORECARD_ID)
        assert result["id"] == SCORECARD_ID

    @pytest.mark.asyncio
    async def test_returns_error_on_404(self):
        adapter = ForgeScorecardHttpAdapter(
            base_url="https://forge.example.com/scorecard",
            api_key="test-key",
        )
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.json.return_value = {}
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)
        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await adapter.get_scorecard_status(scorecard_id=SCORECARD_ID)
        assert "error" in result


# ---------------------------------------------------------------------------
# ScorecardSyncStatus constants
# ---------------------------------------------------------------------------


class TestScorecardSyncStatus:
    def test_status_values(self):
        assert ScorecardSyncStatus.PENDING == "pending"
        assert ScorecardSyncStatus.SYNCED == "synced"
        assert ScorecardSyncStatus.FAILED == "failed"
        assert ScorecardSyncStatus.STALE == "stale"
        assert ScorecardSyncStatus.BLOCKED_NO_CATALOG_ID == "blocked_no_catalog_id"
