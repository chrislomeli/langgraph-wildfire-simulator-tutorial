"""
world-simulator.agents.cluster.graph

Cluster agent LangGraph subgraph.

Topology
────────
    START → apply_thresholds → route_after_filter
          → gather_request_data → evaluate → route_after_evaluate
          → report_risk → END

Construction
────────────
``build_cluster_agent_graph`` is the only public entry point. It takes
the long-lived dependencies (``PromptRegistry``, optional ``BaseStore``)
that the nodes need and threads them in via the ``make_*`` factories.

There is deliberately no module-level compiled graph here. Compiling at
import time would force every consumer to share a single registry/store
configuration and would also run side-effecting work just to import the
module — both make tests harder and leak state across runs.
"""

import logging

from langgraph.graph import END, START, StateGraph

from agents.cluster.nodes import (
    make_apply_thresholds,
    make_evaluate_node,
    make_gather_request_data,
    make_report_risk_node,
    route_after_evaluate,
    route_after_filter,
)
from agents.cluster.state import ClusterAgentState, StreamingRiskGraph
from agents.commons.agent_dependencies import AgentDependencies

logger = logging.getLogger(__name__)


def build_cluster_agent_graph(
        *,
        agent_deps: AgentDependencies,
) -> StreamingRiskGraph:
    """Compile the cluster agent subgraph.

    Topology
    ────────
        START → apply_thresholds → route_after_filter
              → gather_request_data → evaluate → route_after_evaluate
              → report_risk → END

    Parameters
    ──────────
    agent_deps : AgentDependencies
        DI container with prompt_registry, llm_registry, and optional
        store. The evaluate node uses prompt_registry for the system
        prompt and llm_registry for model lookup.
    """
    builder = StateGraph(ClusterAgentState)

    builder.add_node(
        "apply_thresholds",
        make_apply_thresholds(
            world_engine=agent_deps.world_engine,
        ),
    )
    builder.add_node(
        "gather_request_data",
        make_gather_request_data(world_engine=agent_deps.world_engine),
    )

    builder.add_node(
        "evaluate",
        make_evaluate_node(
            prompt_registry=agent_deps.prompt_registry,
            llm_registry=agent_deps.llm_registry,
            world_engine=agent_deps.world_engine,
        ),
    )
    builder.add_node(
        "report_risk",
        make_report_risk_node(world_engine=agent_deps.world_engine, store=agent_deps.store),
    )

    builder.add_edge(START, "apply_thresholds")
    builder.add_conditional_edges("apply_thresholds", route_after_filter)
    builder.add_edge("gather_request_data", "evaluate")
    builder.add_conditional_edges("evaluate", route_after_evaluate)
    builder.add_edge("report_risk", END)

    return StreamingRiskGraph(builder.compile())
