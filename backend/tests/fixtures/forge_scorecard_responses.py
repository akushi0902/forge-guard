"""Forge Scorecard API mock response fixtures (WO-090).

Covers all relevant status codes and scenarios:
  200/201 Success — successful score publication
  400 Bad Request — malformed payload (no retry)
  401 Unauthorized — invalid API key (no retry)
  404 Not Found   — unknown scorecard_id
  500 Server Error — transient failure (retry)
  Timeout          — connection timeout (retry)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Sample entity IDs
# ---------------------------------------------------------------------------

SCORECARD_ID = "sc-aaaa-bbbb-cccc"
SERVICE_ID = uuid.UUID("11112222-3333-4444-5555-666677778888")
ASSESSMENT_ID = uuid.UUID("20000000-0000-0000-0000-000000000001")

# ---------------------------------------------------------------------------
# Sample assessment score data
# ---------------------------------------------------------------------------

SAMPLE_OVERALL_SCORE = 72.5

SAMPLE_DIMENSION_SCORES: dict = {
    "code_quality": {"score": 80.0, "weight": 0.25},
    "test_coverage": {"score": 65.0, "weight": 0.20},
    "security": {"score": 70.0, "weight": 0.30},
    "documentation": {"score": 75.0, "weight": 0.10},
    "operations_readiness": {"score": 78.0, "weight": 0.15},
}

SAMPLE_ASSESSED_AT = datetime(2026, 8, 13, 10, 0, 0, tzinfo=timezone.utc)

# ---------------------------------------------------------------------------
# Success responses
# ---------------------------------------------------------------------------

SCORECARD_PUBLISH_201 = {
    "id": "pub-1111-2222",
    "scorecard_id": SCORECARD_ID,
    "overall_score": SAMPLE_OVERALL_SCORE,
    "dimensions": [
        {"name": "code_quality", "score": 80.0, "weight": 0.25},
        {"name": "test_coverage", "score": 65.0, "weight": 0.20},
        {"name": "security", "score": 70.0, "weight": 0.30},
        {"name": "documentation", "score": 75.0, "weight": 0.10},
        {"name": "operations_readiness", "score": 78.0, "weight": 0.15},
    ],
    "assessed_at": SAMPLE_ASSESSED_AT.isoformat(),
    "created_at": "2026-08-13T10:00:05Z",
}

SCORECARD_GET_200 = {
    "id": SCORECARD_ID,
    "name": "payments-service Scorecard",
    "dimensions": [
        {"name": "code_quality", "weight": 0.25},
        {"name": "test_coverage", "weight": 0.20},
        {"name": "security", "weight": 0.30},
        {"name": "documentation", "weight": 0.10},
        {"name": "operations_readiness", "weight": 0.15},
    ],
    "latest_scores": {
        "overall": SAMPLE_OVERALL_SCORE,
        "assessed_at": SAMPLE_ASSESSED_AT.isoformat(),
    },
}

# ---------------------------------------------------------------------------
# Error responses
# ---------------------------------------------------------------------------

SCORECARD_400_BAD_REQUEST = {
    "error": "bad_request",
    "message": "overall_score must be between 0 and 100",
}

SCORECARD_401_UNAUTHORIZED = {
    "error": "unauthorized",
    "message": "Invalid or missing API key",
}

SCORECARD_404_NOT_FOUND = {
    "error": "not_found",
    "message": f"Scorecard {SCORECARD_ID!r} does not exist",
}

SCORECARD_500_SERVER_ERROR = {
    "error": "internal_server_error",
    "message": "An unexpected error occurred",
}

# ---------------------------------------------------------------------------
# Publish result dicts (what ForgeScorecardAdapter.publish_score returns)
# ---------------------------------------------------------------------------

PUBLISH_RESULT_SUCCESS = {
    "success": True,
    "status_code": 201,
    "error": None,
    "retryable": False,
}

PUBLISH_RESULT_5XX = {
    "success": False,
    "status_code": 500,
    "error": "HTTP 500",
    "retryable": True,
}

PUBLISH_RESULT_4XX = {
    "success": False,
    "status_code": 400,
    "error": "HTTP 400",
    "retryable": False,
}

PUBLISH_RESULT_TIMEOUT = {
    "success": False,
    "status_code": None,
    "error": "timeout",
    "retryable": True,
}

PUBLISH_RESULT_AUTH_FAILURE = {
    "success": False,
    "status_code": 401,
    "error": "HTTP 401",
    "retryable": False,
}
