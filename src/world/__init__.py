"""
world-simulator.world — the world-service (see [[pod-architecture]]).

The world is the source of truth for the simulation. Each tick the
physics module applies the authored scenario plan to the grid; the
``state_snapshot_log`` accumulates per-tick cell snapshots for DB
writeback; ``tick_events.iter_tick_events`` yields location-only
change notifications for downstream consumers.

The agent (advisory-service) consumes the world through ``WorldView``
(read API) and the tick-event stream — never by reaching into the
engine. See [[pod-architecture]] and [[clean-data-no-sensor-noise]].

This package is pure simulation: deterministic (given a plan),
stateful, and fast enough to generate thousands of scenarios offline.
No LangGraph, no LLM, no agent logic.
"""

from world.cell_state import CellState as CellState
from world.cell_state import GenericCell as GenericCell
from world.directions import SECTOR_ANGLES as SECTOR_ANGLES
from world.directions import SECTOR_VECTORS as SECTOR_VECTORS
from world.directions import Direction as Direction
from world.environment import EnvironmentState as EnvironmentState
from world.generic_engine import GenericGroundTruthSnapshot as GenericGroundTruthSnapshot
from world.generic_engine import GenericWorldEngine as GenericWorldEngine
from world.generic_grid import GenericTerrainGrid as GenericTerrainGrid
from world.grid import FireState as FireState
from world.grid import TerrainType as TerrainType
from world.physics import PhysicsModule as PhysicsModule
from world.physics import StateEvent as StateEvent
from world.scenario_store import ScenarioStore as ScenarioStore
from world.sector_analysis import HotspotSectors as HotspotSectors
from world.sector_analysis import SectorSummary as SectorSummary
from world.sector_analysis import StopReason as StopReason
from world.sector_analysis import analyze_sector as analyze_sector
from world.sector_analysis import format_stop_reason as format_stop_reason
from world.sector_analysis import is_wind_aligned as is_wind_aligned
from world.sector_analysis import trace_sector as trace_sector
from world.state_snapshot import CellStateSnapshot as CellStateSnapshot
from world.tick_events import TickChangeEvent as TickChangeEvent
from world.tick_events import iter_tick_events as iter_tick_events
from world.world_view import WorldView as WorldView

__all__ = [
    "CellState",
    "CellStateSnapshot",
    "Direction",
    "EnvironmentState",
    "FireState",
    "GenericCell",
    "GenericGroundTruthSnapshot",
    "GenericTerrainGrid",
    "GenericWorldEngine",
    "HotspotSectors",
    "PhysicsModule",
    "SECTOR_ANGLES",
    "SECTOR_VECTORS",
    "ScenarioStore",
    "SectorSummary",
    "StateEvent",
    "StopReason",
    "TerrainType",
    "TickChangeEvent",
    "WorldView",
    "analyze_sector",
    "format_stop_reason",
    "is_wind_aligned",
    "iter_tick_events",
    "trace_sector",
]
