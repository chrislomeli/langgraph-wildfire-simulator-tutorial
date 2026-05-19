"""Step 6b: CellStateManager.update() projects kept-strongest values onto
the world grid. Lives in its own file because tests/test_cell_state_manager.py
is module-skipped pending an API port — so this is the only running coverage
of the grid write-back.
"""

import pytest

from world.cell_state_manager import CellStateManager
from world.domains.wildfire import FireCellState
from world.generic_grid import GenericTerrainGrid
from world.transport import SensorEvent


def make_event(source_id, source_type, payload, *, confidence=0.95, row=None, col=None):
    metadata = {}
    if row is not None:
        metadata["grid_row"] = row
    if col is not None:
        metadata["grid_col"] = col
    return SensorEvent.create(
        source_id=source_id,
        source_type=source_type,
        cluster_id="c-test",
        payload=payload,
        confidence=confidence,
        sim_tick=0,
        metadata=metadata,
    )


@pytest.fixture
def grid():
    return GenericTerrainGrid(
        rows=4, cols=4, initial_state_factory=lambda r, c, layer: FireCellState()
    )


class TestGridWriteBack:
    def test_temperature_written_to_grid_cell(self, grid):
        mgr = CellStateManager(world_grid=grid)
        mgr.update(make_event("t1", "temperature", {"celsius": 47.0}, row=3, col=3))
        assert grid.get_cell(3, 3).cell_state.temperature_c == 47.0

    def test_wind_event_writes_both_speed_and_direction(self, grid):
        mgr = CellStateManager(world_grid=grid)
        mgr.update(
            make_event("w1", "wind", {"speed_mps": 12.0, "direction_deg": 270.0},
                       row=1, col=1)
        )
        st = grid.get_cell(1, 1).cell_state
        assert st.wind_speed_mps == 12.0
        assert st.wind_direction_deg == 270.0

    def test_keep_strongest_is_what_lands_on_grid(self, grid):
        mgr = CellStateManager(world_grid=grid)
        mgr.update(make_event("strong", "temperature", {"celsius": 50.0},
                              confidence=0.95, row=2, col=2))
        mgr.update(make_event("weak", "temperature", {"celsius": 10.0},
                              confidence=0.10, row=2, col=2))
        # Weaker later reading must not clobber the strong one on the grid.
        assert grid.get_cell(2, 2).cell_state.temperature_c == 50.0
        assert mgr.get_snapshot(2, 2).metrics["temperature"].value == 50.0

    def test_no_grid_is_safe_noop(self):
        # world_grid defaults to None (e.g. unit tests, stateless contexts):
        # update() must not raise and must still track the snapshot.
        mgr = CellStateManager()
        mgr.update(make_event("t1", "temperature", {"celsius": 33.0}, row=0, col=0))
        assert mgr.get_snapshot(0, 0).metrics["temperature"].value == 33.0
