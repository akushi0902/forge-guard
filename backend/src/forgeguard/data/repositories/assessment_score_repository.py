"""AssessmentScoreRepository — typed persistence for RiskScoreResult.

Wraps the existing ScoreRepository with a save_risk_score() method that
accepts a RiskScoreResult and stores it in the assessment_scores table
with score_type='risk', dimension_scores as JSONB, and contributing_factors
as JSONB.

The assessment_scores table was created by migration 0004 (WO-009).  No new
migration is required.
"""

from __future__ import annotations

import json
import uuid
from decimal import Decimal
from typing import Any

import asyncpg
import structlog

from forgeguard.data.repositories.scores import ScoreRepository
from forgeguard.services.release_guardian.models import RiskScoreResult

logger = structlog.get_logger(__name__)


class AssessmentScoreRepository(ScoreRepository):
    """Extends ScoreRepository with methods specific to risk score persistence.

    Args:
        pool: asyncpg connection pool (same as ScoreRepository).
    """

    async def save_risk_score(
        self,
        assessment_id: uuid.UUID,
        service_id: uuid.UUID,
        result: RiskScoreResult,
    ) -> dict[str, Any]:
        """Persist a RiskScoreResult to the assessment_scores table.

        Args:
            assessment_id: UUID of the parent assessment record.
            service_id:    UUID of the service being assessed.
            result:        The RiskScoreResult produced by RiskScorer.

        Returns:
            The inserted row as a dict (from RETURNING *).
        """
        contributing_factors_payload: list[dict[str, Any]] = [
            f.model_dump() for f in result.contributing_factors
        ]

        data: dict[str, Any] = {
            "id": uuid.uuid4(),
            "assessment_id": assessment_id,
            "service_id": service_id,
            "score_type": "risk",
            "overall_score": Decimal(str(result.overall_score)),
            "dimension_scores": json.dumps(result.dimension_scores),
            "contributing_factors": json.dumps(contributing_factors_payload),
        }

        try:
            row = await self.create(data)
            logger.info(
                "assessment_score_repository.risk_score_saved",
                assessment_id=str(assessment_id),
                service_id=str(service_id),
                overall_score=result.overall_score,
            )
            return row
        except Exception as exc:
            logger.error(
                "assessment_score_repository.save_failed",
                assessment_id=str(assessment_id),
                service_id=str(service_id),
                error=str(exc),
            )
            raise

    async def get_latest_risk_score(
        self,
        service_id: uuid.UUID,
    ) -> dict[str, Any] | None:
        """Return the most recent risk score for a service.

        Args:
            service_id: UUID of the service.

        Returns:
            The latest risk score row as a dict, or None if not found.
        """
        return await self.get_latest_score(service_id, "risk")
