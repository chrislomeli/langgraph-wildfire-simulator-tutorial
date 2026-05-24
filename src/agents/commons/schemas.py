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


# ── Spatial primitives ────────────────────────────────────────────────────────


class Corner(BaseModel):
    row: int
    col: int


class SpreadRegion(BaseModel):
    upper_left_corner: Corner
    lower_left_corner: Corner
    upper_right_corner: Corner
    lower_right_corner: Corner


# ── Evaluation / Escalation ───────────────────────────────────────────────────


class Evaluation(BaseModel):
    """Fire risk score for an individual cell."""

    escalate: bool = Field(
        description="TRUE if there is adequate risk that the fire could ignite and spread to the point that we need to plan now"
    )
    ignition_risk: int = Field(
        ge=0,
        le=10,
        description="The risk of a fire starting at the anchor cell ",
    )
    potential_spread_area: SpreadRegion | None = Field(
        description="bounding box of a potential spread area expressed as (row,column) corners",
        default=None,
    )
    confidence: int = Field(
        ge=0,
        le=3,
        description="confidence in risk_score",
    )
    reasoning: list[str] = Field(
        default_factory=list,
        description="""What drove the assessment: e.g. ['temp=52°C (>38 threshold)',
                    'humidity=12% (<15 critical)', 'terrain=grassland (high fuel)',,
                    'fire has fuel and conditions to spread 10 cells to the NE""",
    )


class Escalation(Evaluation):
    """Evaluation result anchored to a specific grid cell."""

    sector_id: str
    row: int
    col: int
    layer: int


# ── Cluster agent I/O ─────────────────────────────────────────────────────────


class EvaluationCell(BaseModel):
    row: int
    col: int
    layer: int
    attributes: dict
    state: FireCellState
