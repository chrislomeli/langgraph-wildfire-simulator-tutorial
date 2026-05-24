"""
world-simulator.agents.supervisor.state

State schema for the supervisor LangGraph.

What is the supervisor?
────────────────────────
The supervisor owns the analysis workflow for one batch of triggered
locations:

  1. Receive a batch of CollatedRecords grouped by cluster.
  2. Fan out to cluster agents via the Send API (parallel execution).
  3. Wait for ALL cluster agents to finish (synchronization barrier).
  4. Assess the overall situation across clusters.
  5. Decide which actuator commands to issue.
  6. Dispatch commands.

Reducers
────────
escalations : operator.add — concatenates each cluster's escalation.
briefings / scenarios / evaluated : operator.or_ — per-cell dict merge.
messages : Standard add_messages — appends, never overwrites.

Node responsibilities
──────────────────────
  fan_out_to_clusters : Conditional-edge function (not a node) that returns
                        list[Send] — one Send per active cluster.
  run_cluster_agent   : Invokes the cluster subgraph; lifts escalations,
                        briefings, and scenarios into supervisor state.
  assess_situation    : Stub — summarises escalations across clusters.
  dispatch_commands   : Stub — logs the plan; final node before END.
"""

from __future__ import annotations

import operator
from typing import Annotated, NewType

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph
from pydantic import Field

from agents.commons.schemas import (
    Escalation,
    TracedState,
)
from controllers.schemas import UpdatedCell

# ── Typed graph ────────────────────────────────────────────────────
SupervisorGraph = NewType("SupervisorGraph", CompiledStateGraph)


# ── Supervisor state ─────────────────────────────────────────────────────────


class SupervisorState(TracedState):
    """
    The internal working state for one supervisor graph execution.

    One execution = one batch of CollatedRecords from the orchestrator.
    """

    # ── Input ────────────────────────────────────────────────────────
    updates: list[UpdatedCell] = Field(default_factory=list)
    escalations: Annotated[list[Escalation], operator.add] = Field(default_factory=list)
    briefings: Annotated[dict, operator.or_] = Field(default_factory=dict)
    scenarios: Annotated[dict, operator.or_] = Field(default_factory=dict)
    evaluated: Annotated[dict, operator.or_] = Field(default_factory=dict)

    # ── LLM reasoning (reserved for when the LLM is wired in) ────────
    messages: Annotated[list[BaseMessage], add_messages] = Field(default_factory=list)

    # ── Situation summary ────────────────────────────────────────────
    situation_summary: str | None = None

    # ── Logistics plan (written by run_logistics_agent node) ─────────
    logistics_plan: str | None = None
