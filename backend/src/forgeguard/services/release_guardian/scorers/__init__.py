"""Dimension-specific risk scorers for Release Guardian (WO-046).

Each scorer is a pure function:  score(metrics) → (score: int, factors: list)
No side effects, no I/O, fully deterministic.
"""
from forgeguard.services.release_guardian.scorers.complexity_scorer import ComplexityScorer
from forgeguard.services.release_guardian.scorers.coverage_scorer import CoverageScorer
from forgeguard.services.release_guardian.scorers.dependency_scorer import DependencyScorer
from forgeguard.services.release_guardian.scorers.security_scorer import SecurityScorer

__all__ = [
    "ComplexityScorer",
    "CoverageScorer",
    "DependencyScorer",
    "SecurityScorer",
]
