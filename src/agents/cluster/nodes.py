"""
world-simulator.agents.cluster.nodes

Node functions for the cluster agent's risk assessment pipeline.

Pipeline shape
──────────────
    START → apply_thresholds → route_after_filter
          → gather_request_data → evaluate → route_after_evaluate
          → report_risk → END

    apply_thresholds    : Deterministic gate. Computes heuristic score for the
                          incoming cell; skips LLM path if score < threshold.
    gather_request_data : Fetches grid bounds, hotspot-sector narrative, and
                          weather forecast/trend for the evaluate node.
    evaluate            : AI boundary. Stub mode returns deterministic scores;
                          LLM mode calls the model with structured output.
    report_risk         : Terminal node. Marks pipeline COMPLETED.
                          (store persistence is a stub — not yet wired.)

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

from langchain_core.messages import HumanMessage
from langgraph.store.base import BaseStore

from agents.cluster.state import ClusterAgentState
from agents.commons.node_executor import node_executor
from agents.commons.routing import route_base
from agents.commons.schemas import (
    AxisFactors,
    Colors,
    Escalation,
    Evaluation,
    EvaluationCell,
    EvaluatorLLMRequest,
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

    @node_executor("apply_thresholds")
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
            f.temperature_c >= 15,
            f.humidity_pct < 10,
            f.vegetation > 0.1,
            f.wind_speed_mps > 3,
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
                "heuristic_score": heuristic,
                "selected_cell": selected_cell,
                "status": StatusValue.PROCESSING,
            }
        else:
            return {
                "heuristic_score": heuristic,
                "status": StatusValue.COMPLETED,
            }

    return apply_thresholds


# ── Node: gather request data ─────────────────────────────────────────────────
def make_gather_request_data(
        world_engine: GenericWorldEngine,
):
    """Factory for the gather_request_data LangGraph node.

    Fetches the context the evaluate node needs: grid bounding box,
    hotspot-sector narrative, weather forecast, and historical trend.
    Writes directly into state; evaluate reads from there.
    """

    @node_executor("gather_request_data")
    def gather_request_data(state: ClusterAgentState):
        evaluate_cell: EvaluationCell = state.selected_cell
        if not evaluate_cell:
            logger.warning("ClusterAgent evaluate: no cells to evaluate")
            return {
                "escalation": None,
                "status": StatusValue.COMPLETED,
            }

        row_boundary, column_boundary = world_engine.get_bounding()
        row, col = evaluate_cell.row, evaluate_cell.col

        # Short-range radial trace — burnable distance + barriers around anchor.
        hotspot_sectors = world_engine.hotspot_sectors(row, col, max_miles=50.0)

        # provide a weather forecast
        briefing = world_engine.create_briefing(row, col)
        forecast = briefing["forecast"]
        trend = briefing["history"]
        return {
            "row_boundary": row_boundary,
            "column_boundary": column_boundary,
            "trend": trend,
            "forecast": forecast,
            "scenario_text": hotspot_sectors.to_context_string(),
        }

    return gather_request_data


# ── Node: evaluate ────────────────────────────────────────────────────────────


async def call_evaluate_llm(
    llm_request: EvaluatorLLMRequest,
    *,
    prompt_registry: PromptRegistry,
    llm_registry: LLMRegistry,
    trial_only: bool = False,
) -> tuple[Escalation | None, int]:
    """Core LLM evaluation call shared by the cluster node and the eval harness.

    Returns ``(Escalation, token_count)``.  token_count is 0 in trial mode.
    Returns ``(None, 0)`` when the LLM fails to produce a parseable result.

    Keeping this as a plain async function (not a factory closure) means the
    eval harness can import and call it directly with the same prompt/model
    path that the live graph uses.
    """
    evaluate_cell = llm_request.cell
    row, col = evaluate_cell.row, evaluate_cell.col

    system_prompt = prompt_registry.render(
        "evaluate",
        context=dict(
            sector_id=llm_request.id,
            max_rows=llm_request.max_rows,
            max_columns=llm_request.max_cols,
            row=row,
            column=col,
            scenario=llm_request.scenario_text,
            trend=json.dumps(llm_request.trend, indent=2),
            forecast=json.dumps(llm_request.forecast, indent=2),
        ),
    )
    human_prompt = (
        f"Readings for ANCHOR cell ({row},{col})\n"
        + evaluate_cell.model_dump_json(indent=2)
    )

    if trial_only:
        evaluation = Evaluation(
            factors=AxisFactors(
                temperature_humidity="stub — not evaluated",
                wind="stub — not evaluated",
                fuel_and_terrain="stub — not evaluated",
                moisture_trend="stub — not evaluated",
            ),
            reasoning="stub — not evaluated",
            escalate=True,
        )
        tokens = 0
    else:
        llm = llm_registry.get("classifier")
        out = await llm.with_structured_output(
            Evaluation, method="function_calling", include_raw=True
        ).ainvoke([
            llm_registry.make_system_message("classifier", system_prompt),
            HumanMessage(human_prompt),
        ])
        evaluation = out.get("parsed")
        if evaluation is None:
            return None, 0
        raw = out.get("raw")
        tokens = getattr(getattr(raw, "usage_metadata", None), "total_tokens", 0) or 0

    escalation = Escalation(
        row=evaluate_cell.row,
        col=evaluate_cell.col,
        layer=evaluate_cell.layer,
        sector_id=llm_request.id,
        scenario_text=llm_request.scenario_text,
        **evaluation.model_dump(),
    )
    return escalation, tokens


def make_call_evaluate_llm(
    prompt_registry: PromptRegistry,
    llm_registry: LLMRegistry,
    trial_only: bool,
):
    """Wrap call_evaluate_llm as a state-dict-returning closure for the LangGraph node."""
    async def _node_call(llm_request: EvaluatorLLMRequest) -> dict:
        escalation, _ = await call_evaluate_llm(
            llm_request,
            prompt_registry=prompt_registry,
            llm_registry=llm_registry,
            trial_only=trial_only,
        )
        if escalation is None:
            return {"escalation": None,
                    "error": "No escalation output returned from llm",
                    "status": StatusValue.ERROR}
        return {
            "evaluated": llm_request.cell.state.model_dump(),
            "escalation": escalation,
            "status": StatusValue.PROCESSING,
        }

    return _node_call


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
    async def evaluate(state: ClusterAgentState) -> dict:
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
        # get the cell we are evaluating
        evaluate_cell: EvaluationCell = state.selected_cell
        if not evaluate_cell:
            logger.warning("ClusterAgent evaluate: no cells to evaluate")
            return {
                "escalation": None,
                "status": StatusValue.PROCESSING,
            }

        # console logging for development only
        if STUB_RISK_SCORE:
            print(f"""\n{Colors.YELLOW}● CALLING LLM STUB {Colors.RESET}""")
        else:
            print(f"""\n{Colors.BLUE}● CALLING LLM  {Colors.RESET}""")

        # create the input for the real worker
        llm_request = EvaluatorLLMRequest(
            cell=state.selected_cell,
            id=state.sector_id,
            max_rows=state.row_boundary,
            max_cols=state.column_boundary,
            scenario_text=state.scenario_text,
            forecast=state.forecast,
            trend=state.trend
        )

        # create the llm caller function
        llm_function = make_call_evaluate_llm(
            prompt_registry=prompt_registry,
            llm_registry=llm_registry,
            trial_only=STUB_RISK_SCORE
        )

        # call the llm
        return await llm_function(llm_request=llm_request)

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
        """Terminal node — marks pipeline complete.

        STUB: store persistence is not yet implemented.
        state.escalation is available here when wiring is added.
        """
        return {"status": StatusValue.COMPLETED}

    return report_risk


# ── Routers ──────────────────────────────────────────────────────────────────
def route_after_filter(state: ClusterAgentState) -> str:
    """Conditional edge router after apply_thresholds.

    Delegates to route_base:
      - status == ERROR     → END
      - status == COMPLETED → END  (cell below threshold, skip LLM)
      - otherwise           → "gather_request_data"
    """
    return route_base(state, next_node="gather_request_data")


def route_after_evaluate(state: ClusterAgentState) -> str:
    """Conditional edge router after evaluate.

    Delegates to route_base:
      - status == ERROR     → END
      - status == COMPLETED → END
      - otherwise           → "report_risk"
    """
    return route_base(state, next_node="report_risk")
