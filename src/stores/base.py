"""Backend-agnostic data-access contracts.

`DataStore` is the facade injected into scenario loaders. It exposes
per-collection repository handles (terrain, scenario_plan, wildfires,
resources, advisories), each defined as an ABC so concrete backends
(Postgres today; SQLite/JSON in the future) implement the same surface.

Agent wiring depends on these abstractions only — concrete `PgGateway`
no longer leaks past the `stores/postgres/` subpackage.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from stores.schemas import Resource, ScenarioPlanSegment, Terrain, WildfireActivity
    from world.domains.wildfire.cell_state import FireCellState
    from world.state_snapshot import CellStateSnapshot


@dataclass
class TerrainConfig:
    """Physics configuration from the terrain table (optional overrides)."""

    cell_size_ft: float | None = None
    time_step_min: float | None = None
    burn_duration_ticks: int | None = None


class CellStateRepository(ABC):
    """Manages the mutable working copy of cell_state.

    `cell_state` holds named groups of state in its `version` column:
    `'seed'` is the immutable source; a working copy (e.g. `'simulation'`)
    is created from seed and then mutated by a simulation run.
    """

    @abstractmethod
    def bootstrap(self, region: str, version: str, seed_version: str = "seed") -> int:
        """Reset the working copy: delete `version` rows, copy from `seed_version`.
        Returns the number of rows copied. Must refuse to target the seed group."""
        ...

    @abstractmethod
    def write_state(
        self, region: str, version: str, snapshots: list[CellStateSnapshot]
    ) -> int:
        """UPDATE the working-copy rows to match the snapshots' current state.

        `cell_state` has one row per (version, grid_row, grid_column, layer,
        region) — no tick column — so this writes 'current' state; the latest
        snapshot per cell wins. Returns the number of rows updated."""
        ...


class TerrainRepository(ABC):
    @abstractmethod
    def fetch_terrain(
        self,
        region_name: str,
        version: str = "seed",
        limit: int | None = None,
    ) -> tuple[dict[tuple[int, int, int], Terrain], TerrainConfig]: ...

    @abstractmethod
    def fetch_cell_location(
        self, row: int, col: int, layer: int = 0
    ) -> tuple[float, float] | None: ...

    @abstractmethod
    def build_fire_cell_state(self, terrain: Terrain) -> FireCellState: ...


class WildfireRepository(ABC):
    @abstractmethod
    def fetch_similar_fires(
        self, min_acres: int, max_acres: int, limit: int = 10
    ) -> list[WildfireActivity]: ...

    @abstractmethod
    def fetch_by_fire_name(self, fire_name: str, limit: int = 5) -> list[WildfireActivity]: ...


class ResourceRepository(ABC):
    @abstractmethod
    def save_collection(self, resources: list[Resource]) -> int: ...

    @abstractmethod
    def fetch_resources_with_commitments(
        self, lat: float, long: float, radius_miles: float
    ) -> list[dict]: ...


class AdvisoryRepository(ABC):
    # Records are produced by the agent layer (ResourceAdvisoryRecord). Typed
    # as Any here to keep stores/ free of agent imports.
    @abstractmethod
    def save_advisory(self, advisory: Any) -> int: ...

    @abstractmethod
    def save_advisories(self, advisories: list[Any]) -> int: ...

    @abstractmethod
    def fetch_recent_advisories(
        self, grid_row: int, grid_col: int, limit: int = 10
    ) -> list[Any]: ...


class ScenarioPlanRepository(ABC):
    @abstractmethod
    def fetch_plan(
        self, region_name: str
    ) -> dict[tuple[int, int, int], list[ScenarioPlanSegment]]: ...


class DataStore(ABC):
    """Top-level facade exposing per-collection repository handles."""

    @property
    @abstractmethod
    def cell_state(self) -> CellStateRepository: ...

    @property
    @abstractmethod
    def terrain(self) -> TerrainRepository: ...

    @property
    @abstractmethod
    def wildfires(self) -> WildfireRepository: ...

    @property
    @abstractmethod
    def resources(self) -> ResourceRepository: ...

    @property
    @abstractmethod
    def advisories(self) -> AdvisoryRepository: ...

    @property
    @abstractmethod
    def scenario_plan(self) -> ScenarioPlanRepository: ...

    def open(self) -> None: ...
    def close(self) -> None: ...
