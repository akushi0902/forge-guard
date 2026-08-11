"""Risk scoring test fixtures — 10 pre-defined ChangeAnalysisResult inputs with manually
calculated expected RiskScoreResult values (WO-046).

Each fixture is a tuple of (ChangeAnalysisResult, expected_overall_score).
Import RISK_SCORING_FIXTURES for regression tests.
"""
from tests.fixtures.risk_scoring.fixtures import RISK_SCORING_FIXTURES

__all__ = ["RISK_SCORING_FIXTURES"]
