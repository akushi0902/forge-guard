"""Generic envelope model that wraps any demo payload with simulation indicators.

Usage::

    from forgeguard.api.schemas.demo_wrapper import DemoResponseEnvelope
    from forgeguard.api.schemas.demo import TransactionResponse

    envelope = DemoResponseEnvelope[TransactionResponse](data=tx_response)
    # envelope.is_simulated == True
    # envelope.data_classification == "simulated"
    # envelope.simulation_disclaimer == SIMULATION_DISCLAIMER

The three simulation indicator fields are:
  * is_simulated       — boolean flag for frontend conditional rendering
  * data_classification — Literal "simulated" for machine-readable filtering
  * simulation_disclaimer — human-readable text required by compliance PRD

Non-demo payloads should never be wrapped with this envelope — callers are
responsible for ensuring only demo-originated data uses this class.
"""

from __future__ import annotations

from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from forgeguard.constants.demo import DATA_CLASSIFICATION_SIMULATED, SIMULATION_DISCLAIMER

T = TypeVar("T")


class DemoResponseEnvelope(BaseModel, Generic[T]):
    """Generic wrapper that annotates any demo payload with simulation metadata.

    Args:
        data: The inner response payload of any type T.
        is_simulated: Always True for demo-generated data (default).
        data_classification: Machine-readable tag, always "simulated".
        simulation_disclaimer: Compliance-required human-readable disclaimer.
    """

    model_config = ConfigDict(
        populate_by_name=True,
        extra="forbid",
    )

    data: T
    is_simulated: bool = Field(default=True, description="Always true for demo data.")
    data_classification: Literal["simulated"] = Field(
        default=DATA_CLASSIFICATION_SIMULATED,
        description="Machine-readable simulation classification.",
    )
    simulation_disclaimer: str = Field(
        default=SIMULATION_DISCLAIMER,
        description="Human-readable compliance disclaimer.",
    )
