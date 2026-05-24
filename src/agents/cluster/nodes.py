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
    Corner,
    Escalation,
    Evaluation,
    EvaluationCell,
    SpreadRegion,
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
STUB_RISK_SCORE = False

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
        uc: UpdatedCell = state.updated_cell

        updated_cell = world_engine.get_cell(uc.row, uc.col)
        if not updated_cell:
            logger.error(f"Coordinate cell {uc.model_dump_json()} does not exist ")
            return {
                "status": StatusValue.ERROR,
            }

        f: FireCellState = updated_cell.cell_state
        factors = [
            f.temperature_c > 32,
            f.humidity_pct < 15,
            f.vegetation < 0.50,
            f.wind_speed_mps > 20,
        ]
        heuristic = round(sum(factors) / len(factors) * 10)
        if heuristic >= HEURISTIC_EVALUATE_THRESHOLD:
            selected_cell = EvaluationCell(
                row=updated_cell.row,
                col=updated_cell.col,
                layer=updated_cell.layer,
                state=updated_cell.cell_state,
                attributes=updated_cell.attributes,
            )
            return {
                "heuristic_score": round(sum(factors) / len(factors) * 10),
                "selected_cell": selected_cell,
                "status": StatusValue.PROCESSING,
            }
        else:
            return {
                "heuristic_score": round(sum(factors) / len(factors) * 10),
                "status": StatusValue.COMPLETED,
            }

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
        evaluate_cell: EvaluationCell = state.selected_cell
        if not evaluate_cell:
            logger.warning("ClusterAgent evaluate: no cells to evaluate")
            return {
                "escalation": None,
                "status": StatusValue.PROCESSING,
            }

        max_rows, max_columns = world_engine.get_bounding()
        row, col, layer = evaluate_cell.row, evaluate_cell.col, 0

        # provide a breakdown of conditions surrounding the changed cell
        scenario = world_engine.get_spread_risk_summary(row, col)

        # provide a weather forecast
        briefing = world_engine.create_briefing(row, col)
        forecast = briefing["forecast"]
        history = briefing["history"]

        system_prompt = prompt_registry.render(
            "evaluate",
            context=dict(
                sector_id=state.sector_id,
                max_rows=max_rows,
                max_columns=max_columns,
                row=row,
                column=col,
                scenario=json.dumps(scenario, indent=2),
                history=json.dumps(history, indent=2),
                forecast=json.dumps(forecast, indent=2),
            ),
        )
        human_prompt = (
            f"Readings for ANCHOR cell ({evaluate_cell.row},{evaluate_cell.col})"
            + evaluate_cell.model_dump_json(indent=2)
        )

        # Split on heuristic score — only call the LLM for cells that have at
        # least one risk factor present. Cells below the threshold are assigned
        # risk_score=0 with high confidence: the heuristic says nothing is there.
        if STUB_RISK_SCORE:
            print(f"""\n{Colors.YELLOW}● CALLING LLM STUB {Colors.RESET}""")
            evaluation = Evaluation(
                escalate=True,
                ignition_risk=5,
                potential_spread_area=SpreadRegion(
                    upper_left_corner=Corner(row=row, col=col),
                    upper_right_corner=Corner(row=row, col=col),
                    lower_left_corner=Corner(row=row, col=col),
                    lower_right_corner=Corner(row=row, col=col),
                ),
                confidence=3,
                reasoning=["this is a dummy escalation"],
            )
        else:
            print(f"""\n{Colors.BLUE}● CALLING LLM  {Colors.RESET}""")
            llm = llm_registry.get("classifier")
            # method="function_calling" instead of OpenAI's strict json_schema mode:
            # SpreadRegion's tuple[int,int] corners render as JSON-schema arrays
            # using prefixItems, which strict structured-output rejects ("array
            # schema missing items"). Function calling accepts the tuple schema.
            evaluation = await llm.with_structured_output(
                Evaluation, method="function_calling"
            ).ainvoke(
                [
                    SystemMessage(system_prompt),
                    HumanMessage(human_prompt),
                ]
            )

        escalation = Escalation(
            row=evaluate_cell.row,
            col=evaluate_cell.col,
            layer=evaluate_cell.layer,
            sector_id=state.sector_id,
            **evaluation.model_dump(),
        )

        eval_dict = evaluate_cell.state.model_dump()

        if escalation.escalate:
            print(
                f"""\nPROMOTE:: {Colors.TEAL}{escalation.model_dump_json(indent=2)}{Colors.RESET}"""
            )
            return {
                "evaluated": {(row, col, 0): eval_dict},
                "briefing": {(row, col, layer): briefing},
                "scenario": {(row, col, layer): scenario},
                "escalation": escalation,
                "status": StatusValue.PROCESSING,
            }
        else:
            print(
                f"""\n{Colors.YELLOW} DEFER:: {escalation.model_dump_json(indent=2)}{Colors.RESET}"""
            )
            return {
                "evaluated": {(row, col, 0): eval_dict},
                "briefing": {(row, col, layer): briefing},
                "scenario": {(row, col, layer): scenario},
                "escalation": escalation,
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
