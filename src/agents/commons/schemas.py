"""
world-simulator.agents.commons.schemas

Cross-agent data contracts for the risk assessment pipeline.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from agents.commons.node_types import NodeError
from agents.commons.state_types import StatusValue
from world.domains.wildfire import FireCellState


class Colors:
    BLUE = "\033[94m"
    GREEN = "\033[32m"
    TEAL = "\033[96m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    RESET = "\033[0m"


# ── Base state ───────────────────────────────────────────────────────────────


class TracedState(BaseModel):
    """
    Minimum contract that node_executor requires from any graph state.

    All agent state classes inherit from this (directly or indirectly)
    to get the three fields that the execution framework needs:
      - session_id: for request tracing across nodes
      - status: for the state machine (idle/processing/completed/error)
      - error: for structured error capture on exception
    """

    session_id: str | None = Field(
        default=None, description="Request correlation ID for tracing across nodes/graphs"
    )
    status: StatusValue = Field(default=StatusValue.IDLE, description="Current state machine value")
    error: NodeError | None = Field(
        default=None, description="Structured error record if last node raised exception"
    )


# ── Evaluation / Escalation ───────────────────────────────────────────────────


class AxisFactors(BaseModel):
    """Per-axis observations — scaffolding that forces explicit attention on every
    dimension before the agent commits to a synthesis. Each field is an observation,
    not a conclusion. The Evaluation.reasoning field is where conclusions are drawn."""

    temperature_humidity: str = Field(
        description=(
            "Observed temperature and humidity readings. "
            "Cite actual values and any thresholds crossed (e.g. >38°C, <15% RH)."
        ),
    )
    wind: str = Field(
        description=(
            "Observed wind speed and direction. Note alignment with open fuel corridors "
            "and flag if direction is shifting or inconsistent across nearby cells."
        ),
    )
    fuel_and_terrain: str = Field(
        description=(
            "Terrain type, vegetation density, and fuel continuity. "
            "Identify natural firebreaks (rock, water, road) or unbroken fuel runs."
        ),
    )
    moisture_trend: str = Field(
        description=(
            "Fuel moisture reading and D-scenario classification (D1–D4). "
            "Note recent precipitation and forecast precip probability."
        ),
    )


class Evaluation(BaseModel):
    """Fire risk score for an individual cell."""

    factors: AxisFactors = Field(
        description="Per-axis observations. Populate all four before writing reasoning.",
    )
    reasoning: str = Field(
        description=(
            "Synthesis across all factors. Identify the decisive tradeoff(s): "
            "which factors support escalation, which suppress it, and which tips the decision."
        ),
    )
    escalate: bool = Field(
        description="TRUE if there is adequate risk that the fire could ignite and spread to the point that we need to plan now"
    )


# ── Escalation ─────────────────────────────────────────────────────────
class Escalation(Evaluation):
    """Evaluation result anchored to a specific grid cell.

    scenario_text carries the radial sector analysis the cluster agent
    used when making its decision — the logistics agent gets the same
    spatial context without re-deriving it from the grid.
    """
    sector_id: str
    row: int
    col: int
    layer: int
    scenario_text: str = ""


# ── EvaluationCell ─────────────────────────────────────────────────────────
class EvaluationCell(BaseModel):
    row: int
    col: int
    layer: int
    attributes: dict
    state: FireCellState


# ── Cluster agent I/O ─────────────────────────────────────────────────────────
class EvaluatorLLMRequest(BaseModel):
    id: str
    cell: EvaluationCell
    scenario_text: str
    forecast: dict | list  # dict = production NWS envelope; list = eval flat periods
    trend: dict | list     # dict = production NWS envelope; list = eval flat periods
    max_rows: int = 0
    max_cols: int = 0
