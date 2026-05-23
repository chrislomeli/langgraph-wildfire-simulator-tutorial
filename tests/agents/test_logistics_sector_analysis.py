"""Tests for the sector_analysis node in agents.logistics.

The node no longer discovers hotspots by scanning the grid for
``CellRiskAssessment`` records. It consumes the ``Escalation`` objects the
cluster agents produced (handed in via ``state.escalations``) and runs a live
8-sector radial trace around each escalated anchor. These tests therefore feed
escalations directly and assert the trace mechanics + combined summary.
"""


import pytest

from agents.commons.schemas import Escalation, SpreadRegion
from agents.commons.state_types import StatusValue
from agents.logistics.nodes import make_sector_analysis_node
from agents.logistics.state import LogisticsAgentState
from world.domains.wildfire.cell_state import FireCellState
from world.generic_grid import GenericTerrainGrid

# ── Self-contained world ──────────────────────────────────────────────────────
#
# These tests build their own grid-backed world rather than the shared `engine`
# fixture, which currently can't instantiate (FirePhysicsModule is abstract after
# the scripted-trend physics migration). sector_analysis only needs a read-only
# world exposing rows/cols/cell_size_ft/get_cell over real, mutable cells.


class _GridWorld:
    """Minimal WorldView over a real GenericTerrainGrid of grassland cells."""

    cell_size_ft = 200.0

    def __init__(self, rows: int = 5, cols: int = 5) -> None:
        self.grid = GenericTerrainGrid(
            rows=rows, cols=cols, initial_state_factory=lambda r, c, l: FireCellState()
        )

    @property
    def rows(self) -> int:
        return self.grid.rows

    @property
    def cols(self) -> int:
        return self.grid.cols

    def get_cell(self, row: int, col: int, layer: int = 0):
        if 0 <= row < self.grid.rows and 0 <= col < self.grid.cols:
            return self.grid.get_cell(row, col, layer)
        return None


@pytest.fixture
def world() -> _GridWorld:
    return _GridWorld()


# ── Helpers ───────────────────────────────────────────────────────────────────


def _escalation(
    row: int,
    col: int,
    ignition_risk: int = 7,
    confidence: int = 2,
    escalate: bool = True,
) -> Escalation:
    """Build an escalation the way the cluster agent would hand one off."""
    return Escalation(
        escalate=escalate,
        ignition_risk=ignition_risk,
        confidence=confidence,
        reasoning=[f"planted hotspot at ({row},{col})"],
        potential_spread_area=SpreadRegion(
            upper_left_corner=(row, col),
            upper_right_corner=(row, col + 1),
            lower_left_corner=(row + 1, col),
            lower_right_corner=(row + 1, col + 1),
        ),
        sector_id=f"sector({row},{col})",
        row=row,
        col=col,
        layer=0,
    )


def _make_state(escalations=None, **overrides) -> LogisticsAgentState:
    base = LogisticsAgentState(
        workflow_id="test-logistics",
        escalations=escalations or [],
    )
    return base.model_copy(update=overrides) if overrides else base


# ── No hotspots ───────────────────────────────────────────────────────────────


class TestSectorAnalysisNoHotspots:
    def test_no_escalations_returns_empty_sector_analysis(self, world):
        node = make_sector_analysis_node(world=world)
        result = node(_make_state())
        assert result["sector_analysis"] == []

    def test_no_escalations_summary_mentions_none(self, world):
        node = make_sector_analysis_node(world=world)
        result = node(_make_state())
        assert "No escalated hotspots" in result["situation_summary"]

    def test_no_escalations_status_is_processing(self, world):
        node = make_sector_analysis_node(world=world)
        result = node(_make_state())
        assert result["status"] == StatusValue.PROCESSING

    def test_non_escalated_hotspot_not_included(self, world):
        """An escalation with escalate=False must not be assessed."""
        node = make_sector_analysis_node(world=world)
        result = node(_make_state(escalations=[_escalation(2, 2, escalate=False)]))
        assert result["sector_analysis"] == []


# ── Single hotspot ────────────────────────────────────────────────────────────


class TestSectorAnalysisSingleHotspot:
    def test_hotspot_produces_one_entry(self, world):
        node = make_sector_analysis_node(world=world)
        result = node(_make_state(escalations=[_escalation(2, 2, ignition_risk=7)]))
        assert len(result["sector_analysis"]) == 1

    def test_hotspot_has_eight_sectors(self, world):
        node = make_sector_analysis_node(world=world)
        result = node(_make_state(escalations=[_escalation(2, 2, ignition_risk=7)]))
        hotspot = result["sector_analysis"][0]
        assert len(hotspot["sectors"]) == 8

    def test_hotspot_epicenter_matches_anchor(self, world):
        node = make_sector_analysis_node(world=world)
        result = node(_make_state(escalations=[_escalation(2, 2, ignition_risk=7)]))
        hotspot = result["sector_analysis"][0]
        assert hotspot["epicenter_row"] == 2
        assert hotspot["epicenter_col"] == 2

    def test_hotspot_risk_score_is_ignition_risk(self, world):
        """HotspotSectors.risk_score is sourced from the escalation's ignition_risk."""
        node = make_sector_analysis_node(world=world)
        result = node(_make_state(escalations=[_escalation(1, 1, ignition_risk=8)]))
        assert result["sector_analysis"][0]["risk_score"] == 8

    def test_situation_summary_contains_hotspot_coords(self, world):
        node = make_sector_analysis_node(world=world)
        result = node(_make_state(escalations=[_escalation(2, 3, ignition_risk=6)]))
        assert "(2, 3)" in result["situation_summary"]

    def test_situation_summary_contains_escalation_reasoning(self, world):
        node = make_sector_analysis_node(world=world)
        result = node(_make_state(escalations=[_escalation(2, 2, ignition_risk=7)]))
        assert "planted hotspot at (2,2)" in result["situation_summary"]

    def test_all_eight_cardinal_directions_present(self, world):
        node = make_sector_analysis_node(world=world)
        result = node(_make_state(escalations=[_escalation(2, 2, ignition_risk=7)]))
        directions = {s["direction"] for s in result["sector_analysis"][0]["sectors"]}
        assert directions == {"N", "NE", "E", "SE", "S", "SW", "W", "NW"}

    def test_sector_burnable_miles_is_non_negative(self, world):
        node = make_sector_analysis_node(world=world)
        result = node(_make_state(escalations=[_escalation(2, 2, ignition_risk=7)]))
        for sector in result["sector_analysis"][0]["sectors"]:
            assert sector["burnable_miles"] >= 0.0

    def test_corner_hotspot_edge_sectors_are_zero(self, world):
        """Hotspot in corner — sectors pointing off-grid should have 0 burnable miles."""
        node = make_sector_analysis_node(world=world)
        result = node(_make_state(escalations=[_escalation(0, 0, ignition_risk=7)]))
        sectors = {s["direction"]: s for s in result["sector_analysis"][0]["sectors"]}
        assert sectors["N"]["burnable_miles"] == 0.0
        assert sectors["NW"]["burnable_miles"] == 0.0
        assert sectors["W"]["burnable_miles"] == 0.0


# ── Multiple hotspots ─────────────────────────────────────────────────────────


class TestSectorAnalysisMultipleHotspots:
    def test_two_escalations_produce_two_entries(self, world):
        node = make_sector_analysis_node(world=world)
        result = node(
            _make_state(
                escalations=[
                    _escalation(0, 0, ignition_risk=6),
                    _escalation(4, 4, ignition_risk=9),
                ]
            )
        )
        assert len(result["sector_analysis"]) == 2

    def test_escalate_flag_filters_correctly(self, world):
        node = make_sector_analysis_node(world=world)
        result = node(
            _make_state(
                escalations=[
                    _escalation(0, 0, ignition_risk=4, escalate=False),  # filtered
                    _escalation(4, 4, ignition_risk=9, escalate=True),
                ]
            )
        )
        assert len(result["sector_analysis"]) == 1
        assert result["sector_analysis"][0]["risk_score"] == 9


# ── stop_reason tests ─────────────────────────────────────────────────────────


class TestSectorAnalysisStopReason:
    def test_each_sector_has_stop_reason(self, world):
        node = make_sector_analysis_node(world=world)
        result = node(_make_state(escalations=[_escalation(2, 2, ignition_risk=7)]))
        for sector in result["sector_analysis"][0]["sectors"]:
            assert "stop_reason" in sector
            assert sector["stop_reason"] is not None

    def test_corner_hotspot_off_grid_sectors_have_grid_edge(self, world):
        """Sectors that immediately leave the grid must report grid_edge."""
        node = make_sector_analysis_node(world=world)
        result = node(_make_state(escalations=[_escalation(0, 0, ignition_risk=7)]))
        sectors = {s["direction"]: s for s in result["sector_analysis"][0]["sectors"]}
        assert sectors["N"]["stop_reason"] == "grid_edge"
        assert sectors["NW"]["stop_reason"] == "grid_edge"
        assert sectors["W"]["stop_reason"] == "grid_edge"

    def test_water_barrier_produces_correct_stop_reason(self, world):
        """A WATER cell directly north of the hotspot stops the N sector."""
        from world.grid import TerrainType
        world.get_cell(1, 2).cell_state.terrain_type = TerrainType.WATER
        node = make_sector_analysis_node(world=world)
        result = node(_make_state(escalations=[_escalation(2, 2, ignition_risk=7)]))
        sectors = {s["direction"]: s for s in result["sector_analysis"][0]["sectors"]}
        assert sectors["N"]["stop_reason"] == "barrier:water"

    def test_urban_barrier_produces_correct_stop_reason(self, world):
        """An URBAN cell directly east of the hotspot stops the E sector."""
        from world.grid import TerrainType
        world.get_cell(2, 3).cell_state.terrain_type = TerrainType.URBAN
        node = make_sector_analysis_node(world=world)
        result = node(_make_state(escalations=[_escalation(2, 2, ignition_risk=7)]))
        sectors = {s["direction"]: s for s in result["sector_analysis"][0]["sectors"]}
        assert sectors["E"]["stop_reason"] == "barrier:urban"

    def test_rock_barrier_produces_correct_stop_reason(self, world):
        from world.grid import TerrainType
        world.get_cell(3, 2).cell_state.terrain_type = TerrainType.ROCK
        node = make_sector_analysis_node(world=world)
        result = node(_make_state(escalations=[_escalation(2, 2, ignition_risk=7)]))
        sectors = {s["direction"]: s for s in result["sector_analysis"][0]["sectors"]}
        assert sectors["S"]["stop_reason"] == "barrier:rock"

    def test_burned_cell_produces_correct_stop_reason(self, world):
        from world.grid import FireState
        world.get_cell(2, 3).cell_state.fire_state = FireState.BURNED
        node = make_sector_analysis_node(world=world)
        result = node(_make_state(escalations=[_escalation(2, 2, ignition_risk=7)]))
        sectors = {s["direction"]: s for s in result["sector_analysis"][0]["sectors"]}
        assert sectors["E"]["stop_reason"] == "burned"

    def test_urban_sector_burnable_miles_excludes_barrier_cell(self, world):
        """The URBAN cell itself is not burnable — miles stop before it."""
        from world.grid import TerrainType
        world.get_cell(2, 3).cell_state.terrain_type = TerrainType.URBAN
        node = make_sector_analysis_node(world=world)
        result = node(_make_state(escalations=[_escalation(2, 2, ignition_risk=7)]))
        sectors = {s["direction"]: s for s in result["sector_analysis"][0]["sectors"]}
        # The barrier is at col 3, one cell east — zero burnable cells before it
        assert sectors["E"]["burnable_miles"] == 0.0
