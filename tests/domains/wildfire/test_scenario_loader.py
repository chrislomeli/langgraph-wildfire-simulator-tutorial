"""physics_mode dispatch + back-compat for load_scenario_from_db.

Uses the mock data store (JSON fixtures); the mock scenario_plan repo
returns an empty plan, so scripted mode yields a fire-free world.
"""

import logging

import pytest

from stores.mock import get_mock_data_store
from world.domains.wildfire import FireState, RothermelFirePhysicsModule, ScriptedTrendPhysics
from world.domains.wildfire.physics import SimpleFirePhysicsModule
from world.domains.wildfire.scenario_loader import (
    load_scenario_from_db,
    load_scenario_from_package,
)

REGION = "lpnf-south"


@pytest.fixture
def data_store():
    return get_mock_data_store()


def _no_cell_burning(engine) -> bool:
    grid = engine.grid
    return all(
        grid.get_cell(r, c).cell_state.fire_state != FireState.BURNING
        for r in range(grid.rows)
        for c in range(grid.cols)
    )


class TestPhysicsModeDispatch:
    def test_default_is_rothermel(self, data_store):
        engine, _ = load_scenario_from_db(REGION, data_store)
        assert isinstance(engine.physics, RothermelFirePhysicsModule)

    def test_legacy_use_rothermel_false_maps_to_simple(self, data_store):
        engine, _ = load_scenario_from_db(REGION, data_store, use_rothermel=False)
        assert isinstance(engine.physics, SimpleFirePhysicsModule)

    def test_explicit_simple(self, data_store):
        engine, _ = load_scenario_from_db(REGION, data_store, physics_mode="simple")
        assert isinstance(engine.physics, SimpleFirePhysicsModule)

    def test_scripted(self, data_store):
        engine, _ = load_scenario_from_db(REGION, data_store, physics_mode="scripted")
        assert isinstance(engine.physics, ScriptedTrendPhysics)

    def test_unknown_mode_raises(self, data_store):
        with pytest.raises(ValueError, match="Unknown physics_mode"):
            load_scenario_from_db(REGION, data_store, physics_mode="bogus")


class TestScriptedForcesNoFire:
    def test_ignition_points_ignored_with_warning(self, data_store, caplog):
        with caplog.at_level(logging.WARNING):
            engine, _ = load_scenario_from_db(
                REGION,
                data_store,
                physics_mode="scripted",
                ignition_points=[{"row": 1, "col": 1, "intensity": 0.9}],
            )
        assert "never start a fire" in caplog.text
        assert _no_cell_burning(engine)


class TestPackageWrapperPassesMode:
    def test_package_wrapper_threads_physics_mode(self, data_store):
        engine, _ = load_scenario_from_package(
            data_store, region_name=REGION, physics_mode="scripted"
        )
        assert isinstance(engine.physics, ScriptedTrendPhysics)
