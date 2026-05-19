"""Deterministic tests for ScriptedTrendPhysics.

No randomness (jitter_sigma defaults to 0), so every value is exact.
"""

import pytest

from stores.schemas import ScenarioPlanSegment
from world import PhysicsModule, StateEvent
from world.domains.wildfire import FireCellState, ScriptedTrendPhysics
from world.domains.wildfire.environment import FireEnvironmentState
from world.generic_grid import GenericTerrainGrid


def seg(**kw) -> ScenarioPlanSegment:
    return ScenarioPlanSegment(**kw)


@pytest.fixture
def environment() -> FireEnvironmentState:
    return FireEnvironmentState()


def make_grid(physics: ScriptedTrendPhysics, rows: int = 3, cols: int = 3):
    return GenericTerrainGrid(
        rows=rows, cols=cols, initial_state_factory=physics.initial_cell_state
    )


def temp(grid, r=0, c=0) -> float:
    return grid.get_cell(r, c).cell_state.temperature_c


class TestContract:
    def test_is_physics_module_subclass(self):
        assert issubclass(ScriptedTrendPhysics, PhysicsModule)

    def test_initial_cell_state_is_default(self):
        st = ScriptedTrendPhysics({}).initial_cell_state(0, 0)
        assert isinstance(st, FireCellState)
        assert st.temperature_c == 30.0 and st.humidity_pct == 25.0

    def test_empty_plan_no_mutation_returns_empty(self, environment):
        phys = ScriptedTrendPhysics({})
        grid = make_grid(phys)
        events = phys.tick_physics(grid, environment, tick=5)
        assert events == []
        assert temp(grid) == 30.0  # untouched seed default

    def test_tick_physics_always_returns_empty(self, environment):
        phys = ScriptedTrendPhysics(
            {(0, 0, 0): [seg(metric="temperature_c", start_tick=0,
                             duration_ticks=4, start_value=10.0, target_value=30.0)]}
        )
        grid = make_grid(phys)
        assert phys.tick_physics(grid, environment, tick=2) == []


class TestLinearRamp:
    def test_inactive_then_ramp_then_hold(self, environment):
        phys = ScriptedTrendPhysics(
            {(0, 0, 0): [seg(metric="temperature_c", start_tick=2, duration_ticks=4,
                             start_value=10.0, target_value=30.0,
                             curve="linear", hold_after=True)]}
        )
        grid = make_grid(phys)
        phys.tick_physics(grid, environment, 0)
        assert temp(grid) == 30.0  # tick<start: untouched (seed default)
        phys.tick_physics(grid, environment, 2)
        assert temp(grid) == 10.0  # p=0 -> start_value
        phys.tick_physics(grid, environment, 4)
        assert temp(grid) == 20.0  # p=0.5 -> midpoint
        phys.tick_physics(grid, environment, 6)
        assert temp(grid) == 30.0  # p=1 (tick==end) -> target
        phys.tick_physics(grid, environment, 9)
        assert temp(grid) == 30.0  # hold_after

    def test_release_freezes_at_target(self, environment):
        phys = ScriptedTrendPhysics(
            {(0, 0, 0): [seg(metric="temperature_c", start_tick=2, duration_ticks=4,
                             start_value=10.0, target_value=30.0,
                             curve="linear", hold_after=False)]}
        )
        grid = make_grid(phys)
        phys.tick_physics(grid, environment, 6)   # end -> 30.0 written
        assert temp(grid) == 30.0
        phys.tick_physics(grid, environment, 7)   # released: no write, frozen
        assert temp(grid) == 30.0


class TestCurves:
    @pytest.mark.parametrize(
        "curve,at_p_half,at_end",
        [("linear", 20.0, 40.0), ("ease_in", 10.0, 40.0),
         ("ease_out", 30.0, 40.0), ("step", 0.0, 40.0)],
    )
    def test_curve_shapes(self, environment, curve, at_p_half, at_end):
        phys = ScriptedTrendPhysics(
            {(0, 0, 0): [seg(metric="temperature_c", start_tick=0, duration_ticks=4,
                             start_value=0.0, target_value=40.0, curve=curve)]}
        )
        grid = make_grid(phys)
        phys.tick_physics(grid, environment, 2)   # p=0.5
        assert temp(grid) == at_p_half
        phys.tick_physics(grid, environment, 4)   # p=1.0
        assert temp(grid) == at_end


class TestStartValueResolution:
    def test_null_start_resolves_from_seed(self, environment):
        phys = ScriptedTrendPhysics(
            {(0, 0, 0): [seg(metric="humidity_pct", start_tick=0, duration_ticks=10,
                             start_value=None, target_value=10.0)]}
        )
        grid = make_grid(phys)
        phys.tick_physics(grid, environment, 0)
        assert grid.get_cell(0, 0).cell_state.humidity_pct == 25.0  # seed
        phys.tick_physics(grid, environment, 5)
        assert grid.get_cell(0, 0).cell_state.humidity_pct == 17.5  # midpoint
        phys.tick_physics(grid, environment, 10)
        assert grid.get_cell(0, 0).cell_state.humidity_pct == 10.0

    def test_null_start_chains_from_predecessor_target(self, environment):
        phys = ScriptedTrendPhysics(
            {(0, 0, 0): [
                seg(metric="temperature_c", start_tick=0, duration_ticks=10,
                    start_value=28.0, target_value=31.0,
                    curve="linear", hold_after=False),
                seg(metric="temperature_c", start_tick=12, duration_ticks=8,
                    start_value=None, target_value=39.0,
                    curve="ease_in", hold_after=True),
            ]}
        )
        grid = make_grid(phys)
        phys.tick_physics(grid, environment, 0)
        assert temp(grid) == 28.0
        phys.tick_physics(grid, environment, 10)
        assert temp(grid) == 31.0                      # phase 1 reaches target
        phys.tick_physics(grid, environment, 11)
        assert temp(grid) == 31.0                      # gap: frozen
        phys.tick_physics(grid, environment, 12)
        assert temp(grid) == 31.0                      # phase 2 p=0 -> chained start
        phys.tick_physics(grid, environment, 16)
        assert temp(grid) == 33.0                      # ease_in p=0.5 -> 0.25
        phys.tick_physics(grid, environment, 20)
        assert temp(grid) == 39.0
        phys.tick_physics(grid, environment, 25)
        assert temp(grid) == 39.0                      # hold_after


class TestMultiMetricAndBounds:
    def test_multi_metric_one_cell(self, environment):
        phys = ScriptedTrendPhysics(
            {(0, 0, 0): [
                seg(metric="temperature_c", start_tick=0, duration_ticks=5,
                    start_value=30.0, target_value=45.0),
                seg(metric="humidity_pct", start_tick=0, duration_ticks=5,
                    start_value=25.0, target_value=10.0),
            ]}
        )
        grid = make_grid(phys)
        phys.tick_physics(grid, environment, 5)
        st = grid.get_cell(0, 0).cell_state
        assert st.temperature_c == 45.0 and st.humidity_pct == 10.0

    def test_clamp_and_wrap(self, environment):
        phys = ScriptedTrendPhysics(
            {(0, 0, 0): [
                seg(metric="temperature_c", start_tick=0, duration_ticks=2,
                    start_value=70.0, target_value=120.0),          # clamps to 80
                seg(metric="wind_direction_deg", start_tick=0, duration_ticks=2,
                    start_value=350.0, target_value=370.0),         # wraps to 10
            ]}
        )
        grid = make_grid(phys)
        phys.tick_physics(grid, environment, 2)
        st = grid.get_cell(0, 0).cell_state
        assert st.temperature_c == 80.0
        assert st.wind_direction_deg == 10.0


class TestSummarize:
    def test_summarize_empty_plan(self):
        phys = ScriptedTrendPhysics({})
        grid = make_grid(phys, rows=2, cols=2)
        s = phys.summarize(grid)
        assert s == {
            "scripted_cells": 0,
            "mean_temperature_c": 30.0,
            "mean_humidity_pct": 25.0,
            "danger_cells": 0,
        }

    def test_summarize_counts_danger(self, environment):
        phys = ScriptedTrendPhysics(
            {(0, 0, 0): [
                seg(metric="temperature_c", start_tick=0, duration_ticks=1,
                    start_value=30.0, target_value=40.0),   # >32
                seg(metric="humidity_pct", start_tick=0, duration_ticks=1,
                    start_value=25.0, target_value=10.0),   # <15
            ]}
        )
        grid = make_grid(phys, rows=2, cols=2)
        phys.tick_physics(grid, environment, 1)
        s = phys.summarize(grid)
        assert s["scripted_cells"] == 1
        assert s["danger_cells"] == 1  # cell (0,0): 2 factors true
