"""
world-simulator.agents.cluster.state

State schema for the cluster agent LangGraph subgraph.

What is a cluster agent?
────────────────────────
One cluster agent runs per geographic/logical cluster of sensors.
Its job is to:
  1. Receive pre-collated records for its cluster (from the orchestrator).
  2. Run the evaluate node to produce per-cell risk assessments.
  3. Report assessments to the report_risk node, which persists them.

The cluster agent is a LangGraph subgraph — it has its own state schema
that is separate from the supervisor's state. The supervisor maps
its own state in/out when it invokes the cluster agent subgraph.

State design principles
────────────────────────
  - Only fields that at least one node reads OR writes belong here.
  - Fields the LLM tool loop needs (messages) use LangGraph's add_messages
    reducer so new messages are appended rather than overwriting the list.
  - Fields are ``X | None`` where they may not be set yet at graph start.

Node responsibilities
──────────────────────
  evaluate    : Reads collated_records; produces escalations (one per
                cell). Stub mode: deterministic placeholder scores. LLM mode:
                single LLM call with structured output (enabled in next milestone).
  report_risk : Persists escalations to the optional store and marks
                the pipeline COMPLETED.
"""

from __future__ import annotations

import operator
import uuid
from typing import Annotated, NewType

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph
from pydantic import Field

from agents.commons.schemas import CellReadings, TracedState, Escalation, EvaluationCell
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
    anchor_layer: int = Field(default=0)

    # ── Messages ─────────────────────────────────────────────────
    # add_messages reducer appends new messages rather than overwriting.
    # evaluate node reads and writes here via the ToolNode loop.
    messages: Annotated[list[BaseMessage], add_messages] = Field(default_factory=list)

    # ── Payloads ─────────────────────────────────────────────────
    updated_cell: UpdatedCell | None = Field(default=None)
    selected_cell: EvaluationCell | None = Field(default=None)
    heuristic_score: int | None = Field(default=None)
    escalation: Escalation | None  = Field(default=None)
    briefing: Annotated[dict, operator.or_] = Field(default_factory=dict)
    scenario: Annotated[dict, operator.or_] = Field(default_factory=dict)

    # ── Legacy ─────────────────────────────────────────────────
    workflow_id: str
    readings: list[CellReadings] = Field(default_factory=list)
