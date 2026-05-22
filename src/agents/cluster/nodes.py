"""
world-simulator.agents.cluster.nodes

Node functions for the cluster agent's risk assessment pipeline.

Pipeline shape
──────────────
    START → update_world → evaluate → route_after_evaluate → report_risk → END

    update_world : Deterministic. Reads grid ground truth for each cell
                   in state.readings (values were written upstream by
                   CellStateManager.update) and produces cell snapshot
                   dicts in state.updated_cells.
    evaluate     : AI boundary. Stub mode returns deterministic placeholder
                   risk scores. LLM mode calls the model with structured
                   output. Both modes write CellRiskAssessment onto each
                   evaluated cell so sector_analysis can find hotspots.
    report_risk  : Terminal node. Persists CollatedRecordRisk records to
                   the optional store and marks the pipeline COMPLETED.

Design principles
─────────────────
  - The AI boundary is explicit: ``evaluate`` is the only node that will
    call an LLM. If the agent produces bad output, debug the prompt and
    tools — not the pipeline structure.
  - Nodes return PARTIAL state updates. LangGraph merges them via reducers.
  - Nodes that need dependencies (prompt registry, LLM, store) are exposed
    as ``make_*`` factories so the graph builder can thread them in at
    compile time — no side effects at import time.
"""

from __future__ import annotations

import json
import logging

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.store.base import BaseStore

from agents.cluster.state import ClusterAgentState
from agents.commons.node_executor import node_executor
from agents.commons.routing import route_base
from agents.commons.schemas import (
    Colors,
    Escalation, EvaluationCell
)
from agents.commons.state_types import StatusValue
from controllers.schemas import UpdatedCell
from llm.llm_registry import LLMRegistry
from prompts import PromptRegistry
from world import GenericWorldEngine
from world.domains.wildfire import FireCellState

logger = logging.getLogger(__name__)

# ── Milestone flag ────────────────────────────────────────────────────────────
#
# True for the dashboard milestone: evaluate returns stub CollatedRecordRisk
# records without calling an LLM. Flip to False in the next milestone once
# the prompt template and LLM tooling are ready.
STUB_RISK_SCORE = True

# ── Heuristic gate ────────────────────────────────────────────────────────────
#
# Cells whose heuristic_score is strictly below this threshold are skipped by
# the evaluate LLM call and assigned risk_score=0 with high confidence.
# The heuristic is 0–10 based on four binary factors (temp, humidity,
# vegetation, wind). A threshold of 1 skips only cells where ALL four factors
# are absent — the most conservative gate, only bypassing obviously safe cells.
HEURISTIC_EVALUATE_THRESHOLD = 3


# ── Node: update world ────────────────────────────────────────────────────────
def make_apply_thresholds(
        world_engine: GenericWorldEngine,
):
    """Factory for the apply_thresholds LangGraph node.

    For each cell in ``state.updated_cells``, recomputes a fire-risk
    heuristic from the current grid state. If any cell meets or exceeds
    ``HEURISTIC_EVALUATE_THRESHOLD``, the node forwards the matching
    ``SelectedCell`` objects to the evaluate node for LLM assessment.

    Returns COMPLETED immediately if no cell crosses the threshold, or
    if none of the qualifying cells can be resolved on the world grid.
    """

    @node_executor("apply_thresholds")  # was "update_world" - name should match the function
    def apply_thresholds(state: ClusterAgentState):
        readings: list[UpdatedCell] = state.updated_cells

        # get_sector drops halo coords that fall outside the grid (edge sectors).
        cells = world_engine.get_sector([(r.row, r.col) for r in readings])

        status = StatusValue.COMPLETED
        for cell in cells:
            f: FireCellState = cell.cell_state
            factors = [
                f.temperature_c > 32,
                f.humidity_pct < 15,
                f.vegetation < 0.50,
                f.wind_speed_mps > 20,
            ]
            heuristic = round(sum(factors) / len(factors) * 10)
            if heuristic >= HEURISTIC_EVALUATE_THRESHOLD:
                status = StatusValue.PROCESSING
                break

        if status == StatusValue.PROCESSING:
            selected_cells = [
                EvaluationCell(
                    row=cell.row,
                    col=cell.col,
                    layer=cell.layer,
                    state=cell.cell_state,
                    attributes=cell.attributes,
                )
                for cell in cells
            ]
            if selected_cells:
                return {
                    "selected_cells": selected_cells,
                    "status": status,
                }

        # No cell crossed the threshold, or the sector resolved to no cells.
        return {"status": StatusValue.COMPLETED}

    return apply_thresholds


# ── Node: evaluate ────────────────────────────────────────────────────────────


def make_evaluate_node(
        prompt_registry: PromptRegistry,
        llm_registry: LLMRegistry,
        world_engine: GenericWorldEngine,
):
    """Factory that creates the evaluate node.

    This is the AI boundary. Everything before this node is deterministic.
    The evaluate node receives cell snapshot dicts from ``update_world`` and
    produces one CollatedRecordRisk per cell. Each risk is also written back
    onto the matching GenericCell.risk_assessment so the logistics agent's
    sector_analysis can find hotspots by scanning the grid.

    Parameters
    ──────────
    prompt_registry : PromptRegistry
        For rendering the system prompt template when LLM mode is active.
    llm_registry : LLMRegistry
        For looking up the LLM to use (role: "classifier") when LLM mode
        is active. Unused in stub mode.
    world_engine : GenericWorldEngine
        The session ground truth. Risk assessments are written onto cells
        in ``world_engine.grid``.
    """

    @node_executor("evaluate")
    async def evaluate(state: ClusterAgentState, max_concurrency: int = 3) -> dict:
        """Evaluate fire risk for every cell snapshot in this cluster.

        Stub mode (STUB_RISK_SCORE=True):
          Returns deterministic placeholder scores — one per cell.
          No LLM is called.

        LLM mode (STUB_RISK_SCORE=False):
          Renders the system prompt, serialises the cell snapshot dicts as
          the human message, and calls the LLM with structured output.

        State reads
        ───────────
          - state.updated_cells : cell snapshot dicts from update_world
          - state.sector_id   : for logging and LLM context

        State writes
        ────────────
          - escalations : list[CollatedRecordRisk], one per cell
          - status           : PROCESSING

        Side effects
        ────────────
          Writes a CellRiskAssessment onto cell.risk_assessment for each
          evaluated cell on the world grid.

        """
        evaluate_cells: list[EvaluationCell] = state.selected_cells
        max_rows, max_columns = world_engine.get_bounding()

        if not evaluate_cells:
            logger.warning("ClusterAgent evaluate: no cells to evaluate")
            return {
                "escalation": None,
                "status": StatusValue.PROCESSING,
            }

        system_prompt = prompt_registry.render(
            "evaluate",
            context=dict(
                sector_id=state.sector_id,
                max_rows=max_rows,
                max_columns=max_columns)
        )
        human_prompt = json.dumps([c.model_dump() for c in evaluate_cells], indent=2)

        # Split on heuristic score — only call the LLM for cells that have at
        # least one risk factor present. Cells below the threshold are assigned
        # risk_score=0 with high confidence: the heuristic says nothing is there.
        if STUB_RISK_SCORE:
            print(f"""\n{Colors.YELLOW}● CALLING LLM STUB {Colors.RESET}""")
            return {
                "escalation": Escalation(
                    sector_id=state.sector_id,
                    escalate=False,
                    confidence=3,
                    contributing_factors=["this is a dummy escalation"]
                ),
                "status": StatusValue.PROCESSING,
            }

        else:
            print(f"""\n{Colors.BLUE}● CALLING LLM  {Colors.RESET}""")
            llm = llm_registry.get("classifier")
            result = await llm.with_structured_output(Escalation).ainvoke(
                [
                    SystemMessage(system_prompt),
                    HumanMessage(human_prompt),
                ]
            )
            if result.escalate is True:
                print(f"""\nPROMOTE:: {Colors.TEAL}{result.model_dump_json(indent=2)}{Colors.RESET}""")
                return {
                    "escalation": result,
                    "status": StatusValue.PROCESSING,
                }
            else:
                print(f"""\n{Colors.YELLOW} DEFER:: {result.model_dump_json(indent=2)}{Colors.RESET}""")
                return {
                    "escalation": result,
                    "status": StatusValue.PROCESSING,
                }

    return evaluate


# ── Node: report_risk ─────────────────────────────────────────────────────────


def make_report_risk_node(world_engine: GenericWorldEngine, store: BaseStore | None = None):
    """Factory that creates the risk reporting node.

    Parameters
    ──────────
    store : BaseStore or None
        Optional LangGraph store. When provided, each CollatedRecordRisk is
        written under (``"escalations"``, sector_id) keyed by
        ``"{row}_{col}"`` for retrieval by the supervisor or a dashboard.
    """

    @node_executor("report_risk")
    def report_risk(state: ClusterAgentState) -> dict:
        """Terminal node — persists risk assessments and marks pipeline complete.

        State reads
        ───────────
          - state.escalations : what to report
          - state.sector_id      : for store namespace

        State writes
        ────────────
          - status : COMPLETED
        """
        escalation = state.escalation
        # assessments = state.escalated_cells
        # sector_id = state.sector_id
        # grid = world_engine.grid
        #
        # for assessment in assessments:
        #     cell = grid.get_cell(assessment.position.row, assessment.position.col)
        #     heuristic = getattr(cell, "heuristic", None)
        #     if heuristic is not None:
        #         divergence = abs(assessment.risk_score - heuristic)
        #         if divergence > 4:
        #             logger.warning(
        #                 "ClusterAgent[%s] heuristic divergence at (%s,%s): llm=%s heuristic=%s delta=%s",
        #                 sector_id,
        #                 assessment.position.row,
        #                 assessment.position.col,
        #                 assessment.risk_score,
        #                 heuristic,
        #                 divergence,
        #             )
        #
        # if store is not None and assessments:
        #     for assessment in assessments:
        #         key = f"{assessment.position.row}_{assessment.position.col}"
        #         store.put(
        #             ("escalations", sector_id),
        #             key,
        #             assessment.model_dump(mode="json"),
        #         )
        #     logger.info(
        #         "ClusterAgent[%s] wrote %d risk assessment(s) to store",
        #         sector_id,
        #         len(assessments),
        #     )
        # else:
        #     logger.info(
        #         "ClusterAgent[%s] completed with %d risk assessment(s)",
        #         sector_id,
        #         len(assessments) if assessments else 0,
        #     )

        return {"status": StatusValue.COMPLETED}

    return report_risk


# ── Routers ──────────────────────────────────────────────────────────────────
def route_after_filter(state: ClusterAgentState) -> str:
    """Conditional edge router after evaluate node.

    Delegates to route_base:
      - status == ERROR     → END
      - status == COMPLETED → END
      - otherwise           → "report_risk"
    """
    return route_base(state, next_node="evaluate")


def route_after_evaluate(state: ClusterAgentState) -> str:
    """Conditional edge router after evaluate node.

    Delegates to route_base:
      - status == ERROR     → END
      - status == COMPLETED → END
      - otherwise           → "report_risk"
    """
    return route_base(state, next_node="report_risk")
