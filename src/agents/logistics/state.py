"""
world-simulator.agents.logistics.state

State schema for the logistics agent LangGraph.

The logistics agent is a ReAct-style tool-calling loop. It receives the
situation summary and cluster findings from the supervisor, calls tools to
gather resource and heatmap data, and produces a deployment plan.

Node responsibilities
─────────────────────
  logistics_agent : Calls the LLM with tools bound. Returns tool calls or
                    a final response.
  tools           : Executes tool calls returned by the LLM (ToolNode).
  extract_plan    : Terminal node — lifts the LLM's final text as the plan.
"""

from __future__ import annotations

import uuid
from typing import Annotated, NewType

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel, Field

from agents.commons.schemas import Escalation, TracedState
from stores.schemas import ResourceAdvisory

LogisticsGraph = NewType("LogisticsGraph", CompiledStateGraph)


class LogisticsAssessment(BaseModel):
    """Structured reasoning trace extracted from the logistics agent's ReAct conversation.

    Produced by a second structured-output call in extract_plan, after the
    ReAct loop completes. Fields are intentionally factual — the agent names
    specific inputs it found or couldn't find, rather than rating its own
    confidence on a numeric scale.

    data_gaps drives branching: an empty list means the agent had what it
    needed; a non-empty list signals that upstream logic should widen the
    search, retry, or escalate to a human.
    """

    observations: list[str] = Field(
        description="Factual findings from the sector analysis and tool results. "
        "One item per distinct finding — do not include inferences here."
    )
    data_gaps: list[str] = Field(
        description="Specific inputs that were missing or unavailable. "
        "Name the gap concretely: 'No available resources found within "
        "30 miles of hotspot (2,3)' not 'resource data was limited'."
    )
    assessment: str = Field(
        description="Reasoning from observations to conclusion. "
        "Explain what the data implied and how you weighted it."
    )
    advisory_rationale: Annotated[str, Field(min_length=10)] = Field(
        description="Explain why a ResourceAdvisory was or was not warranted. Minimum 10 characters."
    )
    advisory: ResourceAdvisory | None = Field(
        default=None,
        description="Populate with a ResourceAdvisory if conditions warrant one; leave null otherwise.",
    )


class LogisticsAgentState(TracedState):
    """Working state for one logistics agent execution.

    One execution = one supervisor tick after cluster agents finish.
    The agent reads heatmap + resources via tools and writes logistics_plan.
    """

    workflow_id: str = Field(default_factory=lambda: str(uuid.uuid4()))  #  todo - if this is supposed to be a tracking value - it's not being used that way?

    # ── Input (populated by supervisor before invoking this graph) ────────────
    situation_summary: str = ""
    # Escalated hotspots from the cluster agents. Each Escalation carries the
    # anchor cell, ignition_risk, confidence, the reasoning that flagged it, and
    # an estimated spread bounding box. The logistics agent assesses these — it
    # does NOT rediscover hotspots by scanning the grid.
    escalations: list[Escalation] = Field(default_factory=list)
    # Per-hotspot context computed upstream by the cluster agent, keyed by
    # (row, col, layer):
    #   scenarios : radial spread-risk summary (engine.get_spread_risk_summary)
    #   briefings : NWS-style weather history + forecast (engine.create_briefing)
    scenarios: dict = Field(default_factory=dict)
    briefings: dict = Field(default_factory=dict)

    # ── Written by sector_analysis node ──────────────────────────────────────
    sector_analysis: list[dict] = Field(default_factory=list)

    # ── LLM conversation — add_messages reducer appends, never overwrites ─────
    messages: Annotated[list[BaseMessage], add_messages] = Field(default_factory=list)

    # ── Output ────────────────────────────────────────────────────────────────
    logistics_plan: str | None = None
    logistics_assessment: LogisticsAssessment | None = None
