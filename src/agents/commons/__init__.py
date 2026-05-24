"""
world-simulator.agents.commons

Public API surface for shared agent infrastructure.

Quick reference:
  - StatusValue  → state machine enum (idle, processing, completed, error)
  - TracedState  → base state class with session_id, status, error
  - LatLon       → real-world coordinate
  - cell_size_miles  → calculate cell dimensions
  - grid_to_latlon   → convert grid (row, col) → real coordinate
  - latlon_to_grid   → convert real coordinate → grid (row, col)
"""

from agents.commons.geo import LatLon, cell_size_miles, grid_to_latlon, latlon_to_grid
from agents.commons.node_executor import node_executor
from agents.commons.node_types import NodeError
from agents.commons.routing import route_base
from agents.commons.schemas import TracedState
from agents.commons.state_types import StatusValue

__all__ = [
    "StatusValue",
    "TracedState",
    "LatLon",
    "cell_size_miles",
    "grid_to_latlon",
    "latlon_to_grid",
    "NodeError",
    "node_executor",
    "route_base",
]
