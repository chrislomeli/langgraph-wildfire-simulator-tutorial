"""Tests for agents.supervisor — state reducers, node functions, graph.

The supervisor is escalation-based now: it fans out one cluster agent per
changed cell (`state.updates`), collects each cluster's `Escalation`, summarises
them, and routes to logistics when any escalated.
"""

from agents.cluster.graph import build_cluster_agent_graph
from agents.cluster.state import ClusterAgentState
from agents.commons.schemas import Escalation
from agents.commons.state_types import StatusValue
from agents.supervisor.nodes import (
    assess_situation,
    make_dispatch_commands,
    make_fan_out_to_clusters,
    make_run_cluster_agent,
    route_after_assess,
)
from agents.supervisor.state import SupervisorState
from controllers.schemas import UpdatedCell

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_state(**overrides) -> SupervisorState:
    base = SupervisorState()
    return base.model_copy(update=overrides) if overrides else base


def _escalation(row: int, col: int, escalate: bool = True, ignition_risk: int = 7) -> Escalation:
    return Escalation(
        escalate=escalate,
        ignition_risk=ignition_risk,
        confidence=2,
        reasoning=["test"],
        potential_spread_area=None,
        sector_id=f"sector({row},{col})",
        row=row,
        col=col,
        layer=0,
    )


def _make_ignitable(engine, row: int, col: int) -> None:
    cs = engine.grid.get_cell(row, col).cell_state
    cs.temperature_c = 50.0
    cs.humidity_pct = 10.0


# ── fan_out_to_clusters tests ─────────────────────────────────────────────────


class TestFanOutToClusters:
    def test_returns_one_send_per_updated_cell(self, agent_deps):
        fan_out = make_fan_out_to_clusters(agent_deps.world_engine)
        state = _make_state(
            updates=[UpdatedCell(row=0, col=0, layer=0), UpdatedCell(row=2, col=3, layer=0)]
        )
        assert len(fan_out(state)) == 2

    def test_empty_updates_returns_empty(self, agent_deps):
        fan_out = make_fan_out_to_clusters(agent_deps.world_engine)
        assert fan_out(_make_state(updates=[])) == []

    def test_send_targets_run_cluster_agent(self, agent_deps):
        fan_out = make_fan_out_to_clusters(agent_deps.world_engine)
        sends = fan_out(_make_state(updates=[UpdatedCell(row=1, col=1, layer=0)]))
        assert sends[0].node == "run_cluster_agent"

    def test_send_payload_is_cluster_state_anchored_to_cell(self, agent_deps):
        fan_out = make_fan_out_to_clusters(agent_deps.world_engine)
        sends = fan_out(_make_state(updates=[UpdatedCell(row=2, col=3, layer=0)]))
        payload = sends[0].arg
        assert isinstance(payload, ClusterAgentState)
        assert (payload.anchor_row, payload.anchor_column) == (2, 3)
        assert (payload.updated_cell.row, payload.updated_cell.col) == (2, 3)


# ── make_run_cluster_agent tests ──────────────────────────────────────────────


class TestRunClusterAgent:
    async def test_default_cell_produces_no_escalation(self, agent_deps):
        run_node = make_run_cluster_agent(build_cluster_agent_graph(agent_deps=agent_deps))
        state = ClusterAgentState(
            anchor_row=0, anchor_column=0, workflow_id="t",
            updated_cell=UpdatedCell(row=0, col=0, layer=0),
        )
        result = await run_node(state)
        assert result["escalations"] == []

    async def test_ignitable_cell_escalates(self, agent_deps):
        _make_ignitable(agent_deps.world_engine, 2, 2)
        run_node = make_run_cluster_agent(build_cluster_agent_graph(agent_deps=agent_deps))
        state = ClusterAgentState(
            anchor_row=2, anchor_column=2, workflow_id="t",
            updated_cell=UpdatedCell(row=2, col=2, layer=0),
        )
        result = await run_node(state)
        assert len(result["escalations"]) == 1
        assert isinstance(result["escalations"][0], Escalation)


# ── assess_situation tests ────────────────────────────────────────────────────


class TestAssessSituation:
    def test_produces_situation_summary(self):
        result = assess_situation(_make_state(escalations=[_escalation(2, 2)]))
        assert result["situation_summary"]

    def test_summary_contains_stub_marker(self):
        result = assess_situation(_make_state())
        assert "[STUB]" in result["situation_summary"]

    def test_status_is_processing(self):
        assert assess_situation(_make_state())["status"] == StatusValue.PROCESSING

    def test_summary_counts_escalated_of_total(self):
        state = _make_state(
            escalations=[_escalation(1, 1, escalate=True), _escalation(2, 2, escalate=False)]
        )
        result = assess_situation(state)
        assert "1 of 2" in result["situation_summary"]


# ── make_dispatch_commands tests ──────────────────────────────────────────────


class TestDispatchCommands:
    def test_sets_completed_status(self):
        dispatch = make_dispatch_commands(store=None)
        assert dispatch(_make_state())["status"] == StatusValue.COMPLETED


# ── route_after_assess tests ─────────────────────────────────────────────────


class TestRouteAfterAssess:
    def test_no_escalations_skips_logistics(self):
        assert route_after_assess(_make_state(escalations=[])) == "dispatch_commands"

    def test_escalation_invokes_logistics(self):
        state = _make_state(escalations=[_escalation(1, 1, escalate=True)])
        assert route_after_assess(state) == "run_logistics_agent"

    def test_only_non_escalated_skips_logistics(self):
        state = _make_state(escalations=[_escalation(1, 1, escalate=False)])
        assert route_after_assess(state) == "dispatch_commands"

    def test_mixed_escalations_invokes_logistics(self):
        state = _make_state(
            escalations=[_escalation(1, 1, escalate=False), _escalation(2, 2, escalate=True)]
        )
        assert route_after_assess(state) == "run_logistics_agent"
