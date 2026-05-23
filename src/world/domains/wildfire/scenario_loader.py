"""
world-simulator.domains.wildfire.scenario_loader

The world-service entry point for wildfire scenarios.

What this does
──────────────
``start_world_service`` reads terrain + cell_state + scenario_cell_plan from
the database and builds a ``GenericWorldEngine`` wired with
``ScriptedTrendPhysics``. The returned engine:

* Satisfies the ``WorldView`` Protocol (read API for consumers).
* Ticks deterministically per the scenario plan.
* Accumulates ``state_snapshot_log`` (full per-cell state per tick, for DB
  writeback — see ``world.state_snapshot``).
* Exposes ``physics.last_changed_cells`` so ``iter_tick_events`` can emit
  ``TickChangeEvent`` notifications on the wire.

What this does NOT do
─────────────────────
* No sensor loading. The world-service does not own sensors. Agents read
  the world through ``WorldView``; sensor abstraction is dead under
  [[clean-data-no-sensor-noise]].
* No ignition. Scripted physics never starts a fire; the agent forecasts
  ignition risk from authored conditions.
* No physics-mode selection. Scripted-only — see [[scripted-trend-driver]].

Geo overlay
───────────
Every cell is stamped with real-world lat/lon coordinates that come
directly from the terrain table. Cells filled with the WATER sentinel
(absent from DB) get bounds-derived lat/lon via ``grid_to_latlon``.

Physics defaults
────────────────
``cell_size_ft`` / ``time_step_min`` / ``burn_duration_ticks`` come from
the terrain table (first non-null wins). Hardcoded fallbacks below are
used only when the DB has no value for a field.
"""

from __future__ import annotations

import logging

from agents.commons.geo import (
    LPNF_SOUTH,
    cell_size_miles,
    grid_to_latlon,
)
from world.domains.wildfire.cell_state import FireCellState, TerrainType
from world.domains.wildfire.environment import FireEnvironmentState
from world.domains.wildfire.scripted_trend_physics import ScriptedTrendPhysics
from world.generic_engine import GenericWorldEngine
from world.generic_grid import GenericTerrainGrid
from world.scenario_store import ScenarioStore

logger = logging.getLogger(__name__)

# ── Fallback defaults (used only when DB has no value) ───────────────────────

_DEFAULT_CELL_SIZE_FT = 6336.0
_DEFAULT_TIME_STEP_MIN = 5.0
_DEFAULT_BURN_DURATION_TICKS = 10

_DEFAULT_ENVIRONMENT = dict(
    temperature_c=30.0,
    humidity_pct=25.0,
    wind_speed_mps=8.0,
    wind_direction_deg=45.0,
    pressure_hpa=1013.0,
)


def _make_water_sentinel() -> FireCellState:
    """Cell state for grid positions absent from the DB.

    WATER terrain with saturated fuel moisture — fire-spread physics treats
    this as non-burnable, so missing cells act as a natural firebreak rather
    than carrying fabricated fuel through gaps in the data.
    """
    return FireCellState(
        terrain_type=TerrainType.WATER,
        vegetation=0.0,
        fuel_moisture=1.0,
        slope=0.0,
        temperature_c=30.0,
        humidity_pct=25.0,
        wind_speed_mps=5.0,
        wind_direction_deg=0.0,
        pressure_hpa=1013.0,
    )


def start_world_service(
    *,
    region_name: str,
    version: str = "simulation",
    data_store: ScenarioStore,
    bounds: dict = LPNF_SOUTH,
    layers: int = 1,
    bootstrap: bool = True,
) -> GenericWorldEngine[FireCellState]:
    """Stand up the world-service for a scenario.

    Parameters
    ──────────
    region_name : DB region key (e.g. 'lpnf-south').
    version     : The cell_state working-copy group this run reads/writes
                  (e.g. 'simulation'). NOT 'seed' — seed is the immutable
                  source. The grid is loaded from this group.
    data_store  : Anything satisfying ScenarioStore — exposes ``.cell_state``,
                  ``.terrain`` and ``.scenario_plan``. The concrete DataStore
                  satisfies this structurally.
    bounds      : Geographic bounding box used only as a fallback for
                  WATER-sentinel cells (no DB row). Defaults to southern
                  Los Padres NF.
    layers      : Number of grid layers (default 1).
    bootstrap   : When True (default), reset the working copy from seed
                  before reading — guarantees a clean, deterministic start.
                  Pass False to resume an existing working copy in place.

    Returns
    ───────
    GenericWorldEngine[FireCellState] wired with ScriptedTrendPhysics. The
    engine satisfies WorldView and exposes ``state_snapshot_log`` for
    writeback and ``physics.last_changed_cells`` for event emission.

    Raises
    ──────
    ValueError : if the DB returns no terrain rows for the region/version.
    """
    # ── Bootstrap the working copy from seed (clean, deterministic start) ─
    if bootstrap:
        data_store.cell_state.bootstrap(region=region_name, version=version)

    # ── Load terrain from DB (joined against the working-copy cell_state) ─
    terrain_repo = data_store.terrain
    terrain_dict, terrain_config = terrain_repo.fetch_terrain(region_name, version=version)

    if not terrain_dict:
        raise ValueError(
            f"No terrain rows found in DB for region {region_name!r} "
            f"version {version!r}. Confirm the terrain table is seeded and "
            f"the {version!r} working copy was bootstrapped from seed."
        )

    # ── Derive grid dimensions from DB rows ──────────────────────
    max_row = max(k[0] for k in terrain_dict) + 1
    max_col = max(k[1] for k in terrain_dict) + 1
    rows, cols = max_row, max_col

    logger.info(
        "Loaded %d terrain cells for region %r — grid %dx%d",
        len(terrain_dict),
        region_name,
        rows,
        cols,
    )

    lat_miles, lon_miles = cell_size_miles(rows, cols, bounds)
    logger.info(
        "Grid overlaid on bounds — %dx%d cells, each ~%.1f x %.1f miles",
        rows,
        cols,
        lat_miles,
        lon_miles,
    )

    # ── Physics — scripted only ──────────────────────────────────
    cell_size_ft = terrain_config.cell_size_ft or _DEFAULT_CELL_SIZE_FT
    time_step_min = terrain_config.time_step_min or _DEFAULT_TIME_STEP_MIN
    burn_duration_ticks = terrain_config.burn_duration_ticks or _DEFAULT_BURN_DURATION_TICKS
    plan = data_store.scenario_plan.fetch_plan(region_name)
    physics = ScriptedTrendPhysics(
        plan=plan
    )
    # Expose terrain-derived physics constants so consumers reading
    # ``world.cell_size_ft`` via WorldView get the right value.
    physics.cell_size_ft = cell_size_ft
    physics.time_step_min = time_step_min
    physics.burn_duration_ticks = burn_duration_ticks

    # ── Build grid ───────────────────────────────────────────────
    # The factory is the single seam: DB hit returns the real cell;
    # DB miss returns a WATER sentinel so missing positions form a firebreak
    # instead of carrying fabricated fuel.
    missing_count = 0

    def build_cell_state(r: int, c: int, layer: int = 0) -> FireCellState:
        nonlocal missing_count
        record = terrain_dict.get((r, c, layer))
        if record is None:
            missing_count += 1
            return _make_water_sentinel()
        return terrain_repo.build_fire_cell_state(record)

    grid = GenericTerrainGrid(
        rows=rows,
        cols=cols,
        layers=layers,
        initial_state_factory=build_cell_state,
    )

    if missing_count:
        logger.warning(
            "Filled %d missing cell(s) with WATER sentinel — "
            "DB does not have terrain rows for all grid positions.",
            missing_count,
        )

    # ── Stamp lat/lon attributes (DB value if present, else bounds-derived) ─
    for r in range(rows):
        for c in range(cols):
            for lay in range(layers):
                record = terrain_dict.get((r, c, lay))
                if record is not None:
                    lat, lon = record.lat, record.long
                else:
                    latlon = grid_to_latlon(r, c, rows, cols, bounds)
                    lat, lon = latlon.lat, latlon.lon
                cell = grid.get_cell(r, c, lay)
                cell.attributes["lat"] = lat
                cell.attributes["lon"] = lon

    # ── Environment ──────────────────────────────────────────────
    environment = FireEnvironmentState(**_DEFAULT_ENVIRONMENT)

    # ── Build engine ─────────────────────────────────────────────
    engine = GenericWorldEngine(
        grid=grid,
        environment=environment,
        physics=physics,
    )

    logger.info(
        "world-service ready for scenario %r: %dx%dx%d grid",
        region_name,
        rows,
        cols,
        layers,
    )

    return engine
