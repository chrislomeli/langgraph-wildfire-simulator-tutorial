"""Integration: scripted plan → loader → engine → deterministic grid.

This is the verifiability payoff. With physics_mode="scripted" the world
is fully deterministic ground truth: every scripted cell's weather at
every tick is exactly predictable, and the ignition-risk heuristic
crosses its threshold at a precise, asserted tick.

The plan is injected through a thin DataStore wrapper (mock store for
terrain/sensors; fixed plan for scenario_plan) so the test needs no
Postgres. Assertions are on engine.grid (ground truth) — NOT through
sensors, whose noise is deliberately non-deterministic by design.
"""

import pytest

from stores.mock import get_mock_data_store
from stores.schemas import ScenarioPlanSegment
from world.domains.wildfire.scenario_loader import load_scenario_from_db

REGION = "lpnf-south"


def _seg(**kw) -> ScenarioPlanSegment:
    return ScenarioPlanSegment(**kw)


# Cell (0,0): heat + dry, both linear over ticks 5..25, then hold.
# Cell (0,1): two-phase temperature — released phase 1, then ease_in
#             phase 2 whose start chains from phase 1's target.
PLAN = {
    (0, 0, 0): [
        _seg(metric="temperature_c", start_tick=5, duration_ticks=20,
             start_value=30.0, target_value=42.0, curve="linear", hold_after=True),
        _seg(metric="humidity_pct", start_tick=5, duration_ticks=20,
             start_value=25.0, target_value=10.0, curve="linear", hold_after=True),
    ],
    (0, 1, 0): [
        _seg(metric="temperature_c", start_tick=0, duration_ticks=10,
             start_value=28.0, target_value=31.0, curve="linear", hold_after=False),
        _seg(metric="temperature_c", start_tick=12, duration_ticks=18,
             start_value=None, target_value=39.0, curve="ease_in", hold_after=True),
    ],
}


class _PlanRepo:
    def fetch_plan(self, region_name):
        return PLAN


class _PlanStore:
    """Delegates everything to the mock store except scenario_plan."""

    def __init__(self):
        self._base = get_mock_data_store()
        self._plan = _PlanRepo()

    @property
    def scenario_plan(self):
        return self._plan

    def __getattr__(self, name):
        return getattr(self._base, name)


def _build_engine():
    engine, _ = load_scenario_from_db(REGION, _PlanStore(), physics_mode="scripted")
    return engine


def _advance_to(engine, scripted_tick: int):
    """Tick the engine until tick_physics has run for `scripted_tick`."""
    while engine.current_tick <= scripted_tick:
        engine.tick()


def _cell(engine, r, c):
    return engine.grid.get_cell(r, c).cell_state


def _danger_factor_count(state) -> int:
    return sum((
        state.temperature_c > 32,
        state.humidity_pct < 15,
        state.vegetation < 0.50,
        state.wind_speed_mps > 20,
    ))


@pytest.fixture
def engine():
    return _build_engine()


class TestDeterministicRamp:
    def test_cell00_temperature_exact_at_boundaries(self, engine):
        _advance_to(engine, 5)
        assert _cell(engine, 0, 0).temperature_c == 30.0   # p=0 -> start
        _advance_to(engine, 15)
        assert _cell(engine, 0, 0).temperature_c == 36.0   # p=0.5
        _advance_to(engine, 25)
        assert _cell(engine, 0, 0).temperature_c == 42.0   # p=1 -> target
        _advance_to(engine, 30)
        assert _cell(engine, 0, 0).temperature_c == 42.0   # hold_after

    def test_cell00_humidity_exact(self, engine):
        _advance_to(engine, 5)
        assert _cell(engine, 0, 0).humidity_pct == 25.0
        _advance_to(engine, 15)
        assert _cell(engine, 0, 0).humidity_pct == 17.5
        _advance_to(engine, 25)
        assert _cell(engine, 0, 0).humidity_pct == 10.0

    def test_cell01_two_phase_chaining(self, engine):
        _advance_to(engine, 0)
        assert _cell(engine, 0, 1).temperature_c == 28.0
        _advance_to(engine, 10)
        assert _cell(engine, 0, 1).temperature_c == 31.0   # phase 1 target
        _advance_to(engine, 11)
        assert _cell(engine, 0, 1).temperature_c == 31.0   # gap: frozen
        _advance_to(engine, 12)
        assert _cell(engine, 0, 1).temperature_c == 31.0   # phase 2 chains from 31
        _advance_to(engine, 21)
        assert _cell(engine, 0, 1).temperature_c == 33.0   # ease_in p=0.5 -> 0.25
        _advance_to(engine, 30)
        assert _cell(engine, 0, 1).temperature_c == 39.0


class TestHeuristicThresholdCrossing:
    def test_danger_crosses_at_exact_tick(self, engine):
        # tick 18: temp 37.8 (>32) but humidity 15.25 (not <15) -> 1 factor
        _advance_to(engine, 18)
        s18 = _cell(engine, 0, 0)
        assert s18.temperature_c == 37.8
        assert s18.humidity_pct == 15.25
        assert _danger_factor_count(s18) == 1  # not yet danger (needs >=2)

        # tick 19: temp 38.4, humidity 14.5 (<15) -> 2 factors -> danger
        _advance_to(engine, 19)
        s19 = _cell(engine, 0, 0)
        assert s19.temperature_c == 38.4
        assert s19.humidity_pct == 14.5
        assert _danger_factor_count(s19) == 2  # deterministic crossing at tick 19


class TestRunIsReproducible:
    def test_two_independent_runs_match(self):
        e1, e2 = _build_engine(), _build_engine()
        for _ in range(26):
            e1.tick()
            e2.tick()
        a, b = _cell(e1, 0, 0), _cell(e2, 0, 0)
        assert (a.temperature_c, a.humidity_pct) == (b.temperature_c, b.humidity_pct)
        assert a.temperature_c == 42.0 and a.humidity_pct == 10.0
