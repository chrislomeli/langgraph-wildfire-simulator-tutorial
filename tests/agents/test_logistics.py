"""Tests for agents.logistics — graph topology, node functions, routing."""
import pytest
from langchain_core.messages import AIMessage
from langgraph.graph import END
from langgraph.graph.state import CompiledStateGraph

from agents.commons.agent_dependencies import AgentDependencies
from agents.commons.schemas import Escalation, SpreadRegion
from agents.commons.state_types import StatusValue
from agents.logistics.graph import build_logistics_agent_graph
from agents.logistics.nodes import (
    make_logistics_agent_node,
    route_after_logistics_agent,
)
from agents.logistics.state import LogisticsAgentState
from llm.llm_registry import LLMRegistry
from prompts import PromptRegistry
from world import GenericWorldEngine
from world.domains.wildfire import ScriptedTrendPhysics
from world.domains.wildfire.environment import FireEnvironmentState
from world.generic_grid import GenericTerrainGrid

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def agent_deps() -> AgentDependencies:
    """Logistics-only AgentDependencies on a lightweight real engine.

    Overrides the shared agents/conftest `agent_deps` (which builds on the
    `engine` fixture). That fixture currently can't instantiate because
    FirePhysicsModule is abstract after the scripted-trend migration; the
    logistics graph only needs a real GenericWorldEngine for sector_analysis to
    trace, so we build a minimal 5x5 grassland one with ScriptedTrendPhysics.
    """
    physics = ScriptedTrendPhysics(plan={})
    grid = GenericTerrainGrid(
        rows=5, cols=5, initial_state_factory=physics.initial_cell_state
    )
    env = FireEnvironmentState(
        temperature_c=38.0, humidity_pct=12.0, wind_speed_mps=8.0,
        wind_direction_deg=225.0, pressure_hpa=1008.0,
    )
    engine = GenericWorldEngine(grid=grid, environment=env, physics=physics)
    return AgentDependencies(
        llm_registry=LLMRegistry({"logistics": None, "logistics_extract": None}),
        prompt_registry=PromptRegistry(),
        store=None,
        world_engine=engine,
    )


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_state(**overrides) -> LogisticsAgentState:
    base = LogisticsAgentState(workflow_id="test-logistics")
    return base.model_copy(update=overrides) if overrides else base


def _escalation(row: int, col: int, ignition_risk: int = 7) -> Escalation:
    """An escalated hotspot the supervisor would hand to the logistics graph."""
    return Escalation(
        escalate=True,
        ignition_risk=ignition_risk,
        confidence=2,
        reasoning=[f"planted hotspot at ({row},{col})"],
        potential_spread_area=SpreadRegion(
            upper_left_corner=(row, col), upper_right_corner=(row, col + 1),
            lower_left_corner=(row + 1, col), lower_right_corner=(row + 1, col + 1),
        ),
        sector_id=f"sector({row},{col})", row=row, col=col, layer=0,
    )


# ── graph build tests ─────────────────────────────────────────────────────────


class TestBuildLogisticsGraph:
    def test_returns_compiled_graph(self, agent_deps):
        graph = build_logistics_agent_graph(agent_deps=agent_deps)
        assert isinstance(graph, CompiledStateGraph)

    def test_graph_contains_sector_analysis_node(self, agent_deps):
        graph = build_logistics_agent_graph(agent_deps=agent_deps)
        nodes = set(graph.get_graph().nodes.keys())
        assert "sector_analysis" in nodes

    def test_graph_contains_logistics_agent_node(self, agent_deps):
        graph = build_logistics_agent_graph(agent_deps=agent_deps)
        nodes = set(graph.get_graph().nodes.keys())
        assert "logistics_agent" in nodes

    def test_graph_contains_extract_plan_node(self, agent_deps):
        """Phase 2 structured-output node must be wired into the graph."""
        graph = build_logistics_agent_graph(agent_deps=agent_deps)
        nodes = set(graph.get_graph().nodes.keys())
        assert "extract_plan" in nodes

    def test_graph_does_not_contain_complete_node(self, agent_deps):
        graph = build_logistics_agent_graph(agent_deps=agent_deps)
        nodes = set(graph.get_graph().nodes.keys())
        assert "complete" not in nodes

    def test_no_world_engine_raises(self, agent_deps):
        """world_engine is mandatory — every consumer dereferences it
        unguarded (unlike data_store/cell_state_manager, which are
        optional). Building a logistics graph without one must fail
        loudly, not silently degrade."""
        from agents.commons.agent_dependencies import AgentDependencies
        with pytest.raises(Exception):
            deps = AgentDependencies(
                llm_registry=agent_deps.llm_registry,
                prompt_registry=agent_deps.prompt_registry,
                store=None,
                world_engine=None,
            )
            build_logistics_agent_graph(agent_deps=deps)


# ── route_after_logistics_agent tests ────────────────────────────────────────


class TestRouteAfterLogisticsAgent:
    def test_no_messages_routes_to_end(self):
        state = _make_state()
        assert route_after_logistics_agent(state) == END

    def test_plain_ai_message_routes_to_extract_plan(self):
        """No tool_calls means the ReAct loop is done — go to Phase 2, not END."""
        msg = AIMessage(content="Here is the plan.")
        state = _make_state(messages=[msg], status=StatusValue.PROCESSING)
        assert route_after_logistics_agent(state) == "extract_plan"

    def test_ai_message_with_tool_calls_routes_to_tools(self):
        msg = AIMessage(
            content="",
            tool_calls=[{"id": "1", "name": "get_resources_within", "args": {"cell_row": 0, "cell_col": 0, "max_distance_mi": 15}}],
        )
        state = _make_state(messages=[msg], status=StatusValue.PROCESSING)
        assert route_after_logistics_agent(state) == "tools"

    def test_error_status_routes_to_end(self):
        state = _make_state(status=StatusValue.ERROR)
        assert route_after_logistics_agent(state) == END

    def test_completed_status_routes_to_end(self):
        state = _make_state(status=StatusValue.COMPLETED)
        assert route_after_logistics_agent(state) == END


# ── make_logistics_agent_node stub tests ──────────────────────────────────────


class TestLogisticsAgentNodeStub:
    def test_stub_returns_ai_message(self, agent_deps):
        node = make_logistics_agent_node(
            tools=[],
            prompt_registry=agent_deps.prompt_registry,
            llm_registry=agent_deps.llm_registry,
        )
        state = _make_state()
        result = node(state)
        assert len(result["messages"]) == 1
        assert isinstance(result["messages"][0], AIMessage)

    def test_stub_message_has_no_tool_calls(self, agent_deps):
        node = make_logistics_agent_node(
            tools=[],
            prompt_registry=agent_deps.prompt_registry,
            llm_registry=agent_deps.llm_registry,
        )
        state = _make_state()
        result = node(state)
        msg = result["messages"][0]
        assert not getattr(msg, "tool_calls", None)

    def test_stub_sets_completed_status(self, agent_deps):
        node = make_logistics_agent_node(
            tools=[],
            prompt_registry=agent_deps.prompt_registry,
            llm_registry=agent_deps.llm_registry,
        )
        state = _make_state()
        result = node(state)
        assert result["status"] == StatusValue.COMPLETED


# ── full graph integration tests ──────────────────────────────────────────────


class TestLogisticsGraphIntegration:
    async def test_invoke_no_hotspots_completes(self, agent_deps):
        graph = build_logistics_agent_graph(agent_deps=agent_deps)
        state = LogisticsAgentState(workflow_id="test-no-hotspots")
        result = await graph.ainvoke(state)
        assert result["status"] == StatusValue.COMPLETED

    async def test_invoke_no_hotspots_produces_plan(self, agent_deps):
        graph = build_logistics_agent_graph(agent_deps=agent_deps)
        state = LogisticsAgentState(workflow_id="test-no-hotspots")
        result = await graph.ainvoke(state)
        assert result["logistics_plan"] is not None

    async def test_invoke_with_hotspot_completes(self, agent_deps):
        graph = build_logistics_agent_graph(agent_deps=agent_deps)
        state = LogisticsAgentState(
            workflow_id="test-with-hotspot",
            escalations=[_escalation(2, 2, ignition_risk=8)],
        )
        result = await graph.ainvoke(state)
        assert result["status"] == StatusValue.COMPLETED

    async def test_invoke_with_hotspot_situation_summary_populated(self, agent_deps):
        """sector_analysis must write situation_summary before logistics_agent runs."""
        graph = build_logistics_agent_graph(agent_deps=agent_deps)
        state = LogisticsAgentState(
            workflow_id="test-summary",
            escalations=[_escalation(2, 2, ignition_risk=8)],
        )
        result = await graph.ainvoke(state)
        assert result["situation_summary"]
        assert "(2, 2)" in result["situation_summary"]
