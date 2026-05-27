"""
world-simulator.agents.cluster.state

State schema for the cluster agent LangGraph subgraph.

What is a cluster agent?
────────────────────────
One cluster agent runs per geographic/logical cluster of sensors.
Its job is to:
  1. Receive the updated cell written upstream by CellStateManager.
  2. Run apply_thresholds to gate on heuristic score, then gather_request_data
     to assemble LLM context, then evaluate to produce an Escalation.
  3. Pass the Escalation to report_risk.

The cluster agent is a LangGraph subgraph — it has its own state schema
that is separate from the supervisor's state. The supervisor maps
its own state in/out when it invokes the cluster agent subgraph.

State design principles
────────────────────────
  - Only fields that at least one node reads OR writes belong here.
  - Fields are ``X | None`` where they may not be set yet at graph start.

Node responsibilities
──────────────────────
  apply_thresholds  : Gates on heuristic score; produces selected_cell.
  gather_request_data: Fetches bounding box, hotspot sectors, forecast/trend.
  evaluate          : AI boundary. Stub mode returns deterministic scores;
                      LLM mode calls the model with structured output.
  report_risk       : Terminal node — marks the pipeline COMPLETED.
"""

from __future__ import annotations

import uuid
from typing import NewType

from langgraph.graph.state import CompiledStateGraph
from pydantic import Field

from agents.commons.schemas import Escalation, EvaluationCell, TracedState
from controllers.schemas import UpdatedCell

# ── Typed graph ────────────────────────────────────────────────────
StreamingRiskGraph = NewType("StreamingRiskGraph", CompiledStateGraph)


# ── Cluster agent state ───────────────────────────────────────────────────────


class ClusterAgentState(TracedState):
    """
    The internal working state for a single cluster agent execution.

    This state lives inside the LangGraph subgraph.
    It is NOT shared directly with the supervisor — the supervisor
    invokes the subgraph and receives only the output mapping.
    """

    # ── Identity ──────────────────────────────────────────────────────
    sector_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    anchor_row: int
    anchor_column: int
    row_boundary: int | None = Field(default=None)
    column_boundary:  int | None = Field(default=None)
    anchor_layer: int = Field(default=0)

    # ── Payloads ─────────────────────────────────────────────────
    updated_cell: UpdatedCell | None = Field(default=None)
    selected_cell: EvaluationCell | None = Field(default=None)
    heuristic_score: int | None = Field(default=None)
    escalation: Escalation | None = Field(default=None)
    evaluated: dict = Field(default_factory=dict)
    forecast: dict | list = Field(default_factory=dict)
    trend: dict | list = Field(default_factory=dict)
    scenario: dict | None = Field(default_factory=dict)

    error: str | None = Field(default=None)
