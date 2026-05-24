"""
world-simulator.agents.supervisor.nodes

Node functions for the supervisor LangGraph (stub mode).

These are the stateful functions that orchestrate the workflow —
fan out, wait, assess, decide, dispatch. The graph builder
(``add_node``, ``add_edge``, ``compile``) lives in ``graph.py``.

Stub mode produces deterministic output end-to-end so the full graph
topology can be validated and the dashboard pipeline exercised before
LLM reasoning is wired in.

Nodes that depend on long-lived resources (the compiled cluster
subgraph, a LangGraph ``BaseStore``) are exposed as ``make_*``
factories so the graph builder can thread dependencies in at compile
time. This keeps the module free of side effects at import time.
"""

import logging

from langgraph.graph.state import CompiledStateGraph
from langgraph.store.base import BaseStore
from langgraph.types import Send

from agents.cluster.state import ClusterAgentState
from agents.commons.node_executor import node_executor
from agents.commons.state_types import StatusValue
from agents.logistics.state import LogisticsAgentState
from agents.supervisor.state import SupervisorState
from world import GenericWorldEngine

logger = logging.getLogger(__name__)


# ── Conditional edge: dynamic fan-out ────────────────────────────────────────


def make_fan_out_to_clusters(world_engine: GenericWorldEngine):
    """Factory for the dynamic fan-out conditional edge.

    Closes over the world engine so sector geometry (halo expansion and
    merging of overlapping halos) is delegated to ``world_engine.expand_sectors``.
    """

    @node_executor("fan_out_to_clusters")
    def fan_out_to_clusters(state: SupervisorState) -> list[Send]:
        """Dynamic fan-out — one ``Send`` per merged sector.

        NOT a regular node: it is a conditional-edge function attached to
        ``START``. LangGraph runs the returned ``Send``s in parallel, then
        advances to ``assess_situation`` once they complete.
        """
        changed = state.updates
        # sectors = world_engine.expand_sectors([(c.row, c.col) for c in changed])

        logger.info(
            "Supervisor fanning out %d changed cell(s) ",
            len(changed),
        )

        sends: list[Send] = []
        for update_cell in changed:
            sector_id = f"sector({update_cell.row},{update_cell.col})"
            cell_state = ClusterAgentState(
                sector_id=sector_id,
                anchor_row=update_cell.row,
                anchor_column=update_cell.col,
                updated_cell=update_cell,
                error=None,
            )
            sends.append(Send("run_cluster_agent", cell_state))

        return sends

    return fan_out_to_clusters


# ── Stateful nodes (factories) ───────────────────────────────────────────────


def make_run_cluster_agent(cluster_graph: CompiledStateGraph):
    """Factory that closes over the compiled cluster subgraph.

    The supervisor invokes the cluster subgraph once per ``Send`` emitted
    by ``fan_out_to_clusters``. Each invocation's ``escalation`` is lifted
    into the supervisor's ``escalations`` list, which uses an ``operator.add``
    reducer so parallel sends concatenate cleanly.
    """

    @node_executor("run_cluster_agent")
    async def run_cluster_agent(state: ClusterAgentState) -> dict:
        sector_id = state.sector_id
        logger.info("Supervisor invoking cluster agent for cluster=%s", sector_id)

        result: ClusterAgentState = await cluster_graph.ainvoke(state)
        # A cluster that completes below the heuristic gate never reaches
        # evaluate, so escalation/briefing/scenario are never written. Use .get
        # so those clusters contribute nothing rather than raising KeyError.
        escalation = result.get("escalation")
        return {
            "evaluated": result.get("evaluated", {}),
            "briefings": result.get("briefing", {}),
            "scenarios": result.get("scenario", {}),
            "escalations": [escalation] if escalation else [],
        }

    return run_cluster_agent


# ── Stub nodes (the supervisor's own steps) ──────────────────────────────────


@node_executor("assess_situation")
def assess_situation(state: SupervisorState) -> dict:
    """Stub assessor — produces a placeholder situation summary.

    A real implementation will read past incidents from the LangGraph
    Store, call an LLM to correlate findings across clusters, and detect
    cross-cluster patterns (e.g. one large event vs many isolated ones).
    """
    escalations = state.escalations
    escalated = [e for e in escalations if e.escalate]

    summary = f"[STUB] {len(escalated)} of {len(escalations)} sector(s) flagged for escalation."
    if escalated:
        summary += " Escalating: " + ", ".join(e.sector_id for e in escalated) + "."

    return {
        "situation_summary": summary,
        "status": StatusValue.PROCESSING,
    }


def make_run_logistics_agent(logistics_graph: CompiledStateGraph):
    """Factory that closes over the compiled logistics subgraph.

    Builds the initial LogisticsAgentState from the supervisor's situation
    summary and cluster findings, invokes the logistics graph, then lifts the
    resulting plan back into supervisor state.
    """

    @node_executor("run_logistics_agent")
    def run_logistics_agent(state: SupervisorState) -> dict:
        # Hand the logistics agent the hotspots the cluster agents already found
        # and escalated — anchor, ignition_risk, confidence, reasoning, and the
        # spread bounding box — plus the per-hotspot scenario/briefing context.
        escalated = [e for e in state.escalations if e.escalate]
        logistics_state = LogisticsAgentState(
            situation_summary=state.situation_summary or "",
            escalations=escalated,
            scenarios=state.scenarios,
            briefings=state.briefings,
        )
        result = logistics_graph.invoke(logistics_state)
        plan = result.get("logistics_plan")
        logger.info(
            "Logistics agent completed. Plan preview: %s",
            (plan[:120] + "...") if plan and len(plan) > 120 else plan,
        )
        return {"logistics_plan": plan, "status": StatusValue.PROCESSING}

    return run_logistics_agent


def make_dispatch_commands(store: BaseStore | None = None):
    """Factory for the final dispatch node.

    The store parameter is reserved for persisting situation summaries to
    long-term memory once that capability is wired in. Stub mode ignores it.
    """

    @node_executor("dispatch_commands")
    def dispatch_commands(state: SupervisorState) -> dict:
        # Terminal node — stub. Surfaces the logistics plan; a real impl would
        # publish advisories / actuator commands here.
        print("\nDISPATCH FINAL FINDINGS - STUB")
        if state.logistics_plan:
            print(state.logistics_plan)
        return {"status": StatusValue.COMPLETED}

    return dispatch_commands


# ── Routers ──────────────────────────────────────────────────────────────────


def route_after_assess(state: SupervisorState) -> str:
    """Conditional edge after assess_situation.

    Skips the logistics agent entirely when no cluster has a risk score at
    or above the sector_analysis threshold — there are no hotspots to report
    on, so firing the logistics LLM would waste tokens and produce noise.

    Routes to:
      "run_logistics_agent"  — at least one cluster scored >= LOGISTICS_RISK_THRESHOLD
      "dispatch_commands"    — all scores below threshold, or no scores at all
    """
    escalated = [e for e in state.escalations if e.escalate]
    if escalated:
        logger.info(
            "route_after_assess: %d sector(s) escalated — invoking logistics agent",
            len(escalated),
        )
        return "run_logistics_agent"

    logger.info("route_after_assess: no sectors escalated — skipping logistics")
    return "dispatch_commands"
