"""Test fixtures for decision threshold engine (WO-049).

Provides:
    - Sample threshold configurations (default + strict + lenient)
    - Score input matrix covering all three decision outcomes plus edge cases
    - Factory functions for unit and integration tests

Run all threshold engine tests:
    pytest tests/unit/services/decision_engine/ -v
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

# ---------------------------------------------------------------------------
# Stable IDs
# ---------------------------------------------------------------------------

DEFAULT_THRESHOLD_ID = uuid.UUID("f0000000-0000-0000-0000-000000000001")
STRICT_THRESHOLD_ID = uuid.UUID("f0000000-0000-0000-0000-000000000002")
LENIENT_THRESHOLD_ID = uuid.UUID("f0000000-0000-0000-0000-000000000003")

# ---------------------------------------------------------------------------
# Threshold configuration dicts (match DB row shape)
# ---------------------------------------------------------------------------

DEFAULT_THRESHOLD: dict[str, Any] = {
    "id": DEFAULT_THRESHOLD_ID,
    "name": "Default Threshold",
    "approve_health_min": Decimal("70.00"),
    "approve_risk_max": Decimal("30.00"),
    "conditional_health_min": Decimal("50.00"),
    "conditional_risk_max": Decimal("60.00"),
    "is_active": True,
    "created_by": None,
    "updated_by": None,
}

STRICT_THRESHOLD: dict[str, Any] = {
    "id": STRICT_THRESHOLD_ID,
    "name": "Strict Threshold",
    "approve_health_min": Decimal("85.00"),
    "approve_risk_max": Decimal("15.00"),
    "conditional_health_min": Decimal("65.00"),
    "conditional_risk_max": Decimal("40.00"),
    "is_active": False,
    "created_by": None,
    "updated_by": None,
}

LENIENT_THRESHOLD: dict[str, Any] = {
    "id": LENIENT_THRESHOLD_ID,
    "name": "Lenient Threshold",
    "approve_health_min": Decimal("60.00"),
    "approve_risk_max": Decimal("40.00"),
    "conditional_health_min": Decimal("40.00"),
    "conditional_risk_max": Decimal("70.00"),
    "is_active": False,
    "created_by": None,
    "updated_by": None,
}

# ---------------------------------------------------------------------------
# Score input matrix — (health_score, risk_score, expected_decision)
# ---------------------------------------------------------------------------

SCORE_MATRIX: list[tuple[Decimal, Decimal, str]] = [
    # ── APPROVE cases ──────────────────────────────────────────────────
    (Decimal("70"),  Decimal("30"),  "APPROVE"),   # exact boundary
    (Decimal("71"),  Decimal("29"),  "APPROVE"),   # just inside
    (Decimal("100"), Decimal("0"),   "APPROVE"),   # trivial best case
    (Decimal("80"),  Decimal("20"),  "APPROVE"),   # well inside

    # ── CONDITIONAL_APPROVE cases ──────────────────────────────────────
    (Decimal("50"),  Decimal("60"),  "CONDITIONAL_APPROVE"),   # exact boundary
    (Decimal("69"),  Decimal("31"),  "CONDITIONAL_APPROVE"),   # just outside APPROVE
    (Decimal("60"),  Decimal("50"),  "CONDITIONAL_APPROVE"),   # mid-range
    (Decimal("51"),  Decimal("59"),  "CONDITIONAL_APPROVE"),   # just inside conditional

    # ── BLOCK cases ────────────────────────────────────────────────────
    (Decimal("49"),  Decimal("61"),  "BLOCK"),     # both below conditional
    (Decimal("0"),   Decimal("100"), "BLOCK"),     # worst case
    (Decimal("50"),  Decimal("61"),  "BLOCK"),     # health OK but risk too high
    (Decimal("49"),  Decimal("60"),  "BLOCK"),     # risk OK but health too low

    # ── Off-by-one cases ──────────────────────────────────────────────
    (Decimal("69.99"), Decimal("30"),  "CONDITIONAL_APPROVE"),  # just below APPROVE health
    (Decimal("70"),    Decimal("30.01"), "CONDITIONAL_APPROVE"), # just above APPROVE risk
    (Decimal("49.99"), Decimal("60"),  "BLOCK"),                # just below CONDITIONAL health
    (Decimal("50"),    Decimal("60.01"), "BLOCK"),              # just above CONDITIONAL risk
]

# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------

def make_threshold_row(
    *,
    id: uuid.UUID = DEFAULT_THRESHOLD_ID,
    name: str = "Test Threshold",
    approve_health_min: Decimal = Decimal("70.00"),
    approve_risk_max: Decimal = Decimal("30.00"),
    conditional_health_min: Decimal = Decimal("50.00"),
    conditional_risk_max: Decimal = Decimal("60.00"),
    is_active: bool = True,
) -> dict[str, Any]:
    return {
        "id": id,
        "name": name,
        "approve_health_min": approve_health_min,
        "approve_risk_max": approve_risk_max,
        "conditional_health_min": conditional_health_min,
        "conditional_risk_max": conditional_risk_max,
        "is_active": is_active,
        "created_by": None,
        "updated_by": None,
    }
