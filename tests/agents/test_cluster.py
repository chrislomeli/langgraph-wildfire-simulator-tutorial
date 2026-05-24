"""Tests for agents.cluster — state schema, node functions, graph.

The cluster agent is per-anchor-cell now: `apply_thresholds` (graph node
"update_world") gates one `updated_cell` on a heuristic and, if it passes,
selects it; `evaluate` produces a single `Escalation` (stub mode: deterministic)
plus the per-cell briefing/scenario; `report_risk` is terminal.
"""

from langgraph.graph import END
from langgraph.graph.state import CompiledStateGraph

from agents.cluster.graph import build_cluster_agent_graph
from agents.cluster.nodes import (
    make_apply_thresholds,
    make_evaluate_node,
    make_report_risk_node,
    route_after_evaluate,
    route_after_filter,
)
from agents.cluster.state import ClusterAgentState
from agents.commons.schemas import Escalation, EvaluationCell
from agents.commons.state_types import StatusValue
from controllers.schemas import UpdatedCell

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_state(**overrides) -> ClusterAgentState:
    base = ClusterAgentState(anchor_row=0, anchor_column=0)
    return base.model_copy(update=overrides) if overrides else base


def _selected_cell(engine, row: int, col: int) -> EvaluationCell:
    """Build the EvaluationCell apply_thresholds would hand to evaluate."""
    cell = engine.grid.get_cell(row, col)
    return EvaluationCell(
        row=cell.row, col=cell.col, layer=cell.layer,
        state=cell.cell_state, attributes=cell.attributes,
    )


def _make_ignitable(engine, row: int, col: int) -> None:
    """Push a cell past the heuristic gate: hot + dry = 2 of 4 factors → score 5."""
    cs = engine.grid.get_cell(row, col).cell_state
    cs.temperature_c = 50.0  # > 32
    cs.humidity_pct = 10.0   # < 15


# ── ClusterAgentState schema tests ───────────────────────────────────────────


class TestClusterAgentState:
    def test_defaults(self):
        state = ClusterAgentState(anchor_row=1, anchor_column=2)
        assert state.anchor_row == 1
        assert state.anchor_column == 2
        assert state.anchor_layer == 0
        assert state.escalation is None
        assert state.briefing == {}
        assert state.scenario == {}
        assert state.messages == []
        assert state.status == StatusValue.IDLE

    def test_sector_id_has_uuid_default(self):
        state = ClusterAgentState(anchor_row=0, anchor_column=0)
        assert state.sector_id  # non-empty UUID string


# ── apply_thresholds (graph node "update_world") tests ────────────────────────


class TestApplyThresholds:
    def test_below_threshold_completes_without_selecting(self, agent_deps):
        # Default grassland cell — no risk factors → heuristic 0 → COMPLETED.
        node = make_apply_thresholds(world_engine=agent_deps.world_engine)
        result = node(_make_state(updated_cell=UpdatedCell(row=0, col=0, layer=0)))
        assert result["status"] == StatusValue.COMPLETED
        assert result["heuristic_score"] == 0
        assert "selected_cell" not in result

    def test_above_threshold_selects_cell_and_processes(self, agent_deps):
        _make_ignitable(agent_deps.world_engine, 1, 1)
        node = make_apply_thresholds(world_engine=agent_deps.world_engine)
        result = node(_make_state(updated_cell=UpdatedCell(row=1, col=1, layer=0)))
        assert result["status"] == StatusValue.PROCESSING
        assert result["heuristic_score"] >= 3
        assert isinstance(result["selected_cell"], EvaluationCell)
        assert (result["selected_cell"].row, result["selected_cell"].col) == (1, 1)

    def test_missing_cell_errors(self, agent_deps):
        node = make_apply_thresholds(world_engine=agent_deps.world_engine)
        result = node(_make_state(updated_cell=UpdatedCell(row=99, col=99, layer=0)))
        assert result["status"] == StatusValue.ERROR


# ── evaluate node tests ───────────────────────────────────────────────────────


class TestEvaluateNode:
    async def test_stub_produces_escalation(self, agent_deps):
        engine = agent_deps.world_engine
        evaluate = make_evaluate_node(
            prompt_registry=agent_deps.prompt_registry,
            llm_registry=agent_deps.llm_registry,
            world_engine=engine,
        )
        state = _make_state(
            anchor_row=2, anchor_column=2, selected_cell=_selected_cell(engine, 2, 2)
        )
        result = await evaluate(state)
        assert result["status"] == StatusValue.PROCESSING
        esc = result["escalation"]
        assert isinstance(esc, Escalation)
        assert 0 <= esc.ignition_risk <= 10
        assert 0 <= esc.confidence <= 3
        assert (esc.row, esc.col) == (2, 2)

    async def test_writes_briefing_and_scenario_keyed_by_cell(self, agent_deps):
        engine = agent_deps.world_engine
        evaluate = make_evaluate_node(
            prompt_registry=agent_deps.prompt_registry,
            llm_registry=agent_deps.llm_registry,
            world_engine=engine,
        )
        state = _make_state(
            anchor_row=2, anchor_column=3, selected_cell=_selected_cell(engine, 2, 3)
        )
        result = await evaluate(state)
        assert (2, 3, 0) in result["briefing"]
        assert (2, 3, 0) in result["scenario"]


# ── routing tests ─────────────────────────────────────────────────────────────


class TestRouteAfterFilter:
    def test_processing_routes_to_evaluate(self):
        assert route_after_filter(_make_state(status=StatusValue.PROCESSING)) == "evaluate"

    def test_completed_routes_to_end(self):
        assert route_after_filter(_make_state(status=StatusValue.COMPLETED)) == END

    def test_error_routes_to_end(self):
        assert route_after_filter(_make_state(status=StatusValue.ERROR)) == END


class TestRouteAfterEvaluate:
    def test_routes_to_report_risk_when_processing(self):
        assert route_after_evaluate(_make_state(status=StatusValue.PROCESSING)) == "report_risk"

    def test_routes_to_report_risk_when_idle(self):
        assert route_after_evaluate(_make_state()) == "report_risk"

    def test_routes_to_end_on_error(self):
        assert route_after_evaluate(_make_state(status=StatusValue.ERROR)) == END

    def test_routes_to_end_on_completed(self):
        assert route_after_evaluate(_make_state(status=StatusValue.COMPLETED)) == END


# ── report_risk node tests ────────────────────────────────────────────────────


class TestReportRiskNode:
    def test_sets_completed_status(self, agent_deps):
        report_risk = make_report_risk_node(world_engine=agent_deps.world_engine, store=None)
        result = report_risk(_make_state(escalation=None))
        assert result["status"] == StatusValue.COMPLETED


# ── graph integration tests ───────────────────────────────────────────────────


class TestClusterAgentGraph:
    def test_build_returns_compiled_graph(self, agent_deps):
        graph = build_cluster_agent_graph(agent_deps=agent_deps)
        assert isinstance(graph, CompiledStateGraph)

    def test_graph_nodes_are_update_world_evaluate_report_risk(self, agent_deps):
        graph = build_cluster_agent_graph(agent_deps=agent_deps)
        node_names = set(graph.get_graph().nodes.keys())
        assert {"update_world", "evaluate", "report_risk"} <= node_names

    async def test_below_threshold_completes_without_escalation(self, agent_deps):
        graph = build_cluster_agent_graph(agent_deps=agent_deps)
        state = _make_state(
            anchor_row=0, anchor_column=0, updated_cell=UpdatedCell(row=0, col=0, layer=0)
        )
        result = await graph.ainvoke(state)
        assert result["status"] == StatusValue.COMPLETED
        # Below-threshold path never reaches evaluate, so no escalation is written.
        assert result.get("escalation") is None

    async def test_above_threshold_produces_escalation(self, agent_deps):
        _make_ignitable(agent_deps.world_engine, 3, 3)
        graph = build_cluster_agent_graph(agent_deps=agent_deps)
        state = _make_state(
            anchor_row=3, anchor_column=3, updated_cell=UpdatedCell(row=3, col=3, layer=0)
        )
        result = await graph.ainvoke(state)
        assert result["status"] == StatusValue.COMPLETED
        assert isinstance(result["escalation"], Escalation)
        assert (result["escalation"].row, result["escalation"].col) == (3, 3)
