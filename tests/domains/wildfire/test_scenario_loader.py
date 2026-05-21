"""start_world_service contract + tick-event emission.

Verifies the slim world-service entry point: returns an engine wired with
ScriptedTrendPhysics, no sensors, no ignition. Also exercises
iter_tick_events to confirm the event stream carries locations only.
"""

import pytest

from stores.mock import get_mock_data_store
from world import GenericWorldEngine
from world.domains.wildfire import ScriptedTrendPhysics
from world.domains.wildfire.scenario_loader import start_world_service
from world.tick_events import TickChangeEvent, iter_tick_events

REGION = "lpnf-south"


@pytest.fixture
def data_store():
    return get_mock_data_store()


@pytest.fixture
def engine(data_store):
    return start_world_service(region_name=REGION, data_store=data_store)


class TestStartWorldService:
    def test_returns_engine_only(self, engine):
        assert isinstance(engine, GenericWorldEngine)

    def test_engine_uses_scripted_physics(self, engine):
        assert isinstance(engine.physics, ScriptedTrendPhysics)

    def test_engine_satisfies_world_view(self, engine):
        # WorldView surface — rows/cols/cell_size_ft/get_cell
        assert engine.rows > 0
        assert engine.cols > 0
        assert engine.cell_size_ft > 0
        assert engine.get_cell(0, 0) is not None

    def test_state_snapshot_log_empty_before_tick(self, engine):
        assert engine.state_snapshot_log == []

    def test_state_snapshot_log_populates_per_tick(self, engine):
        engine.tick()
        assert len(engine.state_snapshot_log) == engine.rows * engine.cols


class TestIterTickEvents:
    def test_yields_one_event_per_tick(self, engine):
        events = list(iter_tick_events(engine, horizon_ticks=3))
        assert len(events) == 3

    def test_events_are_locations_only(self, engine):
        events = list(iter_tick_events(engine, horizon_ticks=1))
        ev = events[0]
        assert isinstance(ev, TickChangeEvent)
        # Tuple of (row, col, layer) — no state values
        for loc in ev.changed_cells:
            assert isinstance(loc, tuple)
            assert len(loc) == 3
            assert all(isinstance(x, int) for x in loc)

    def test_events_carry_correct_tick(self, engine):
        events = list(iter_tick_events(engine, horizon_ticks=3))
        assert [e.tick for e in events] == [0, 1, 2]

    def test_mock_store_empty_plan_yields_no_changes(self, engine):
        # Mock scenario_plan returns {} → nothing changes per tick.
        events = list(iter_tick_events(engine, horizon_ticks=2))
        assert all(ev.changed_cells == () for ev in events)
